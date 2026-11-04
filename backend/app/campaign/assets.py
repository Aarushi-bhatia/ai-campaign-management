"""Work on one asset: write it, check it, fix it once, edit it by chat or by hand, undo. Every change is a
new version, and each version keeps what its AI calls cost.
"""

import difflib
import json
import logging
import re
from dataclasses import dataclass, field, replace
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai.models import AiCall
from app.ai.service import AiCallFailed, AiService
from app.brand import writing_rules
from app.brand.evidence import Document, normalize, sentences
from app.brand.images import library
from app.brand.images.channel_rules import ABOUT_IMAGES
from app.brand.images.picking import AssetSpec, blocked_reason
from app.brand.models import Brand, BrandFile
from app.campaign import prompts, writer
from app.campaign.brand_tools import BrandTools
from app.campaign.checker import ai_check
from app.campaign.checks import (CHANNEL_OF, FREE_CHECKS, LINK, CheckRules, Problem, forbids_hashtags, free_checks,
                                  is_empty, plain_text)
from app.campaign.models import Asset, AssetVersion, Campaign
from app.campaign.research import approved
from app.config import ModelSize
from app.memory.service import core_texts, recent_images

log = logging.getLogger(__name__)
NO_IMAGE = re.compile(r"^\s*(no image|none|n/a)\b", re.IGNORECASE)
KEPT = "Kept as written: "
"""Marks a flagged problem the fix step found was not a problem, so it is listed but not counted as a fix."""
REPEATED_FIX = 2
"""How many times the same hand fix is made before the agent offers to remember it."""


class NothingToUndo(ValueError):
    pass


class EmptyEdit(Exception):
    """A chat edit came back with no text, which would leave the asset with nothing to publish. Not saved."""


class AssetChanged(Exception):
    """The asset got a new version while this change was being made, so the change was not saved."""


@dataclass
class Draft:
    """What came out of writing or editing an asset, before it is saved."""

    content: dict[str, Any]
    call_ids: list[int] = field(default_factory=list)
    fixed: list[str] = field(default_factory=list)
    warnings: list[dict[str, str]] = field(default_factory=list)
    changed: str = ""
    """For a chat edit: what the edit changed, in one line."""
    saved: bool = True
    """False when a chat edit came back identical, so no new version was made."""
    found: list[dict[str, str]] = field(default_factory=list)
    """What the checks found on the text they were given, before any fix."""


@dataclass
class AssetWork:
    session: Session
    ai: AiService
    brand: Brand
    campaign: Campaign

    def __post_init__(self) -> None:
        self.tools = BrandTools(self.session, self.ai, self.brand, self.campaign.chat_id)
        self._links: frozenset[str] | None = None
        self._rules: dict[str, str] = {}

    # Writing

    def write(self, asset: Asset) -> str:
        """Writes the asset, checks it, tries one fix, and saves both versions. Returns a status line.

        A draft already saved (its checks failed, or a restart cut them off) is never written again: only the
        checks run, so a good draft is neither hidden nor paid for twice."""
        card = self._card(asset)
        if asset.content:
            _, facts = self._lookups(asset, card, record=False)
            return self._check_draft(asset, asset.content, facts)
        self._set_state(asset, "writing")
        rules, facts = self._lookups(asset, card)
        self._choose_image(asset, card)
        research = approved(self.campaign, asset.plan_id)
        reply = self.ai.complete(
            step=f"Write asset {asset.id}: {asset.title}"[:200], size=ModelSize.LARGE,
            prompt=self._prompt(writer.write_task(asset.position + 1, card, asset.image, rules, facts, research)),
            output_schema=writer.schema_for(asset.type), chat_id=self.campaign.chat_id, brand_id=self.brand.id,
            cache_key=f"brand-{self.brand.id}",
        )
        asset.call_id = reply.call_id
        first = writer.content_from(asset.type, json.loads(reply.text))
        self._save(asset, "written", Draft(first, [reply.call_id]))
        return self._check_draft(asset, first, facts)

    def _check_draft(self, asset: Asset, first: dict[str, Any], facts: str) -> str:
        """Checks a saved draft and tries one fix. When the checks themselves fail, the draft stays, shown and
        marked as not checked, so Check again can finish the job."""
        self._set_state(asset, "checking")
        try:
            checked = self.check_and_fix(asset, first, facts)
        except Exception as error:
            log.exception("Checking asset %s failed", asset.id)
            self.session.rollback()
            asset.state, asset.error, asset.fixed = "done", None, []
            asset.warnings = [not_checked(error)]
            self._version(asset).warnings = asset.warnings
            self.session.commit()
            return (f"{writer.TYPE_LABELS[asset.type]} “{asset.title}” written, but its checks couldn't run: {error}. "
                    "Press Check again on it.")
        # The draft was saved before its checks ran; its version now keeps what they found, so going back to it
        # (undo, restore) shows those problems again rather than an empty "passed".
        self._version(asset).warnings = checked.found if checked.content != first else checked.warnings
        if checked.content != first:
            self._save(asset, "auto fix", checked, note="; ".join(checked.fixed))
        else:
            self._set_checks(asset, checked)
        asset.state = "done"
        self.session.commit()
        return self._status_line(asset, checked)

    def check_and_fix(self, asset: Asset, content: dict[str, Any], facts: str) -> Draft:
        """Both checks; when either finds something, one fix, then the free checks again."""
        problems, call_ids = self._all_checks(asset, content, facts)
        if not problems:
            return Draft(content, call_ids)
        found = [p.to_dict() for p in problems]
        reply = self.ai.complete(
            step=f"Fix asset {asset.id}"[:200], size=ModelSize.MEDIUM,
            prompt=self._prompt(writer.fix_task(asset.type, content, [p.to_dict() for p in problems],
                                                approved(self.campaign, asset.plan_id), self._channel_rules(asset),
                                                facts)),
            output_schema=writer.schema_for(asset.type, writer.FIX_EXTRA), chat_id=self.campaign.chat_id,
            brand_id=self.brand.id, cache_key=f"brand-{self.brand.id}",
        )
        raw = json.loads(reply.text)
        fixed = writer.content_from(asset.type, raw)
        still = free_checks(asset.type, fixed, self._check_rules(asset))
        ai_left = [Problem("claim", line) for line in raw["not_fixed"] if line.strip()]
        changes = [line for line in raw["fixed"] if line.strip()]
        changes += [f"{KEPT}{line}" for line in raw["dismissed"] if line.strip()]
        return Draft(fixed, [*call_ids, reply.call_id], changes, [p.to_dict() for p in [*still, *ai_left]], found=found)

    def check_again(self, asset: Asset) -> Draft:
        """The full check on demand, with no fix. Its warnings replace the old ones, but only while the asset is
        still at the version that was checked: a hand edit saved meanwhile keeps its own warnings."""
        checked_version = asset.version
        _, facts = self._lookups(asset, self._card(asset), record=False)
        problems, call_ids = self._all_checks(asset, asset.content or {}, facts)
        current = self.session.scalar(select(Asset.version).where(Asset.id == asset.id).with_for_update())
        if current != checked_version:
            self.session.rollback()
            raise AssetChanged(f"“{asset.title}” changed while it was being checked (it is now at version {current}), "
                               "so these results weren't kept. Press Check again on the latest version.")
        draft = Draft(asset.content or {}, call_ids, warnings=[p.to_dict() for p in problems])
        self._set_checks(asset, draft)
        # The version keeps them too, so going back to it later (undo, restore) shows what this check found,
        # not the list from before it.
        self._version(asset).warnings = draft.warnings
        self.session.commit()
        return draft

    # Editing

    def edit(self, asset: Asset, instruction: str, field_name: str = "") -> Draft:
        """A chat edit: only this asset, and only the named field when there is one. Checked again after."""
        card = self._card(asset)
        rules, facts = self._lookups(asset, card, record=False)
        old, base = asset.content or {}, asset.version
        field_name = field_name if field_name in writer.FIELDS[asset.type] else ""
        reply = self.ai.complete(
            step=f"Edit asset {asset.id}"[:200], size=ModelSize.MEDIUM,
            prompt=self._prompt(writer.edit_task(asset.type, asset.title, old, instruction, field_name, rules, facts,
                                                 approved(self.campaign, asset.plan_id))),
            output_schema=writer.schema_for(asset.type, writer.EDIT_EXTRA), chat_id=self.campaign.chat_id,
            brand_id=self.brand.id, cache_key=f"brand-{self.brand.id}",
        )
        raw = json.loads(reply.text)
        new = writer.content_from(asset.type, raw)
        if field_name:
            new = {**old, field_name: new[field_name]}
        if is_empty(asset.type, new) and not is_empty(asset.type, old):
            raise EmptyEdit(reply.call_id)
        if new == old:
            # Nothing changed: no new version, and no checks to pay for.
            return Draft(old, [reply.call_id], warnings=asset.warnings, changed=raw["changed"].strip(), saved=False)
        try:
            problems, call_ids = self._all_checks(asset, new, facts)
            warnings = [p.to_dict() for p in problems]
        except Exception as error:
            # As when writing: the paid-for edit is kept, marked as not checked, so Check again can finish the job.
            log.exception("Checking the edit of asset %s failed", asset.id)
            call_ids = [error.call_id] if isinstance(error, AiCallFailed) else []
            warnings = [not_checked(error)]
        draft = Draft(new, [reply.call_id, *call_ids], warnings=warnings, changed=raw["changed"].strip())
        self._save(asset, "chat edit", draft, note=draft.changed, expected=base)
        return draft

    def hand_edit(self, asset: Asset, content: dict[str, Any], base: int | None = None) -> tuple[Draft, str | None]:
        """Typed straight into the asset: free checks only, no AI, no cost. Also returns a "Remember this?"
        offer when the same wording change has now been made by hand more than once. `base` is the version the
        typing started from; if the asset has moved on since, nothing is saved."""
        old = asset.content or {}
        content = {key: content.get(key, old.get(key)) for key in (*writer.FIELDS[asset.type], "sources")}
        # Only the free checks run again here. What the AI check found, or that it never ran, still stands
        # until Check again, so a small typed fix can't turn an unchecked asset into "passed"; an AI warning
        # goes once the words it quotes are gone.
        draft = Draft(content, warnings=self._rechecked(asset, content, asset.warnings))
        self._save(asset, "hand edit", draft, expected=asset.version if base is None else base)
        return draft, self._repeated_fix(plain_text(old), plain_text(content))

    def undo(self, asset: Asset, base: int | None = None) -> AssetVersion:
        """Brings back the version before the current one, as a new version."""
        versions = {v.number: v for v in asset.versions}
        current = versions[asset.version]
        target = (current.based_on if current.reason == "undo" else current.number) - 1
        if target < 1:
            raise NothingToUndo("There is no earlier version.")
        old = versions[target]
        asset.image = old.image
        version = self._save(asset, "undo", Draft(old.content, warnings=self._rechecked(asset, old.content, old.warnings)),
                             note=f"Back to version {target}",
                             based_on=target, expected=asset.version if base is None else base)
        return version

    def restore(self, asset: Asset, number: int, base: int | None = None) -> AssetVersion:
        """Brings back any earlier version, as a new version. Nothing is lost, so this can be undone too."""
        versions = {v.number: v for v in asset.versions}
        if number not in versions:
            raise NothingToUndo(f"There is no version {number}.")
        if number == asset.version:
            raise NothingToUndo(f"Version {number} is already showing.")
        old = versions[number]
        asset.image = old.image
        return self._save(asset, "restore", Draft(old.content, warnings=self._rechecked(asset, old.content, old.warnings)),
                          note=f"Back to version {number}",
                          based_on=number, expected=asset.version if base is None else base)

    # Helpers

    def fixed_part(self) -> str:
        return prompts.fixed_part(self.brand.name, self.brand.summary, core_texts(self.session, self.brand.id))

    def _prompt(self, task: str):
        return writer.prompt(self.fixed_part(), self.campaign, task)

    def _card(self, asset: Asset) -> dict[str, Any]:
        cards = {a["id"]: a for a in (self.campaign.plan or {}).get("assets", [])}
        return cards.get(asset.plan_id, {"id": asset.plan_id, "type": asset.type, "title": asset.title})

    def _lookups(self, asset: Asset, card: dict[str, Any], record: bool = True) -> tuple[str, str]:
        channel = CHANNEL_OF[asset.type]
        rules = self._channel_rules(asset)
        facts = self.tools.facts(" ".join(card.get(k, "") for k in ("title", "main_message", "audience")))
        if record:
            count = 0 if facts == "No facts found." else len(json.loads(facts))
            asset.looked_up = [f"{channel.replace('_', ' ')} rules", f"{count} facts"]
        return rules, facts

    def _choose_image(self, asset: Asset, card: dict[str, Any]) -> None:
        """Ranks the images, then saves the choice at once, so the next asset sees it.

        Assets are written a few at a time. The ranking is an AI call, so it runs with nothing locked and
        nothing written; two assets can rank at the same time. Only the reservation after it is locked, and it
        is short: the campaign's row is locked, the images in use are read again, and the best-ranked image
        that no other asset took meanwhile is saved. Two assets can only share an image when none of the
        ranked choices is free."""
        if NO_IMAGE.match(card.get("image_idea", "")):
            asset.image = None
            self.session.commit()
            return
        with self.session.no_autoflush:
            spec = replace(self._spec(asset, card), used_paths=self._images_in_use(asset),
                           recent_paths=recent_images(self.session, self.brand.id, skip_campaign=self.campaign.id),
                           memory=tuple(core_texts(self.session, self.brand.id)))
            result = library.pick(self.session, self.ai, self.brand, spec, chat_id=self.campaign.chat_id,
                                  step=f"Image choice asset {asset.id}")
        self.session.execute(select(Campaign.id).where(Campaign.id == self.campaign.id).with_for_update())
        taken = self._images_in_use(asset)
        choice = next((c for c in result.choices if c.path not in taken), result.choices[0] if result.choices else None)
        asset.image = ({"path": choice.path, "alt_text": choice.alt_text, "why": choice.why} if choice
                       else {"suggestion": result.suggestion})
        self.session.commit()  # ends the reservation

    def _images_in_use(self, asset: Asset) -> frozenset[str]:
        images = self.session.execute(select(Asset.image).where(
            Asset.campaign_id == self.campaign.id, Asset.id != asset.id, Asset.state != "removed")).scalars()
        return frozenset(image["path"] for image in images if image and image.get("path"))

    def _spec(self, asset: Asset, card: dict[str, Any]) -> AssetSpec:
        return AssetSpec(channel=CHANNEL_OF[asset.type], asset_type=asset.type,
                         message=f"{card.get('main_message', '')} Image idea: {card.get('image_idea', '')}",
                         campaign_rules=self._campaign_image_rules())

    def _campaign_image_rules(self) -> str:
        """What the brief and its answers say about images, applied on top of the library's own rules."""
        texts = [self.campaign.brief, *(f"{q['question']} {q.get('answer') or ''}" for q in self.campaign.questions
                                        if q.get("answer")), *self.campaign.brief_rules]
        lines = [line.strip(" -*#>") for text in texts for line in sentences(text) if ABOUT_IMAGES.search(line)]
        return " ".join(dict.fromkeys(line for line in lines if line))

    def _check_rules(self, asset: Asset) -> CheckRules:
        rules = writing_rules.ensure(self.session, self.ai, self.brand)
        return CheckRules(
            banned=rules["banned"], old_names=rules["old_names"], limits=rules["limits"],
            approved_urls=frozenset(f["url"] for f in approved(self.campaign, asset.plan_id)) | self._known_links(),
            image_problem=self._image_problem(asset),
            no_hashtags=forbids_hashtags(json.loads(self._channel_rules(asset)).get("rules", [])),
        )

    def _known_links(self) -> frozenset[str]:
        """Links the brief, its answers or the brand's current documents give. Using them isn't citing."""
        if self._links is None:
            texts = [self.campaign.brief, *(q.get("answer") or "" for q in self.campaign.questions)]
            texts += self.session.scalars(select(BrandFile.text).where(
                BrandFile.brand_id == self.brand.id, BrandFile.kind == "document", BrandFile.status == "current"))
            self._links = frozenset(u.rstrip(".,;") for text in texts if text for u in LINK.findall(text))
        return self._links

    def _image_problem(self, asset: Asset) -> str | None:
        path = (asset.image or {}).get("path")
        if not path:
            return None
        view = next((v for v in library.image_views(self.session, self.brand.id) if v.path == path), None)
        if view is None:
            return "It is no longer in the library."
        return blocked_reason(view, self._spec(asset, self._card(asset)), library.rules_for(self.brand)["channels"])

    def _all_checks(self, asset: Asset, content: dict[str, Any], facts: str) -> tuple[list[Problem], list[int]]:
        free = free_checks(asset.type, content, self._check_rules(asset))
        rules = self._channel_rules(asset)
        found, reply = ai_check(
            self.ai, brand_name=self.brand.name, summary=self.brand.summary,
            campaign=writer.campaign_text(self.campaign),
            asset_label=writer.TYPE_LABELS[asset.type], content=content, facts=facts,
            research=writer.research_text(approved(self.campaign, asset.plan_id)), rules=rules,
            memory=core_texts(self.session, self.brand.id),
            step=f"Check asset {asset.id}", chat_id=self.campaign.chat_id, brand_id=self.brand.id,
        )
        return [*free, *found], [reply.call_id]

    def _save(self, asset: Asset, reason: str, draft: Draft, note: str = "", based_on: int | None = None,
              expected: int | None = None) -> AssetVersion:
        """Saves a new version. The asset's row is locked first, so two saves never get the same number; with
        `expected`, the save only happens if the asset is still at that version (nobody changed it meanwhile)."""
        current = self.session.scalar(select(Asset.version).where(Asset.id == asset.id).with_for_update())
        if expected is not None and current != expected:
            self.session.rollback()
            raise AssetChanged(f"“{asset.title}” changed while this was being done (it is now at version {current}), "
                               "so nothing was saved. Look at the latest version and try again.")
        cost = self.session.scalar(select(func.coalesce(func.sum(AiCall.cost_usd), 0.0))
                                   .where(AiCall.id.in_(draft.call_ids))) if draft.call_ids else 0.0
        latest = self.session.scalar(select(func.max(AssetVersion.number)).where(AssetVersion.asset_id == asset.id))
        number = (latest or 0) + 1
        version = AssetVersion(number=number, reason=reason, note=note, content=draft.content, image=asset.image,
                               warnings=draft.warnings, call_ids=draft.call_ids, cost_usd=cost, based_on=based_on)
        asset.versions.append(version)
        asset.content, asset.version = draft.content, number
        self._set_checks(asset, draft)
        self.session.commit()
        return version

    def _channel_rules(self, asset: Asset) -> str:
        """The channel's rules, looked up once: the writer, the fix, both checks and the edit all get the same."""
        channel = CHANNEL_OF[asset.type]
        if channel not in self._rules:
            self._rules[channel] = self.tools.channel_rules(channel)
        return self._rules[channel]

    @staticmethod
    def _version(asset: Asset) -> AssetVersion:
        return next(v for v in asset.versions if v.number == asset.version)

    def _rechecked(self, asset: Asset, content: dict[str, Any], warnings: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Warnings for text being brought back or typed: the free checks run again on it, and the AI's own
        findings are kept while the words they quote are still there. "Not checked" always stays."""
        text = Document(plain_text(content))
        kept = [w for w in warnings if w["check"] not in FREE_CHECKS
                and (w["check"] == "not checked" or not w.get("quote") or text.contains(w["quote"]))]
        return [*[p.to_dict() for p in free_checks(asset.type, content, self._check_rules(asset))], *kept]

    @staticmethod
    def _set_checks(asset: Asset, draft: Draft) -> None:
        asset.fixed, asset.warnings = draft.fixed, draft.warnings

    def _set_state(self, asset: Asset, state: str) -> None:
        """Saved at once, on purpose: the asset cards poll for "writing" and "checking" while the job runs."""
        asset.state = state
        self.session.commit()

    def _status_line(self, asset: Asset, checked: Draft) -> str:
        image = asset.image or {}
        picture = f"image {image['path']}" if image.get("path") else (
            f"no image ({image['suggestion']})" if image.get("suggestion") else "no image")
        parts = [f"{writer.TYPE_LABELS[asset.type]} “{asset.title}” written. Looked up {', '.join(asset.looked_up)}; {picture}."]
        fixes = [line for line in checked.fixed if not line.startswith(KEPT)]
        if fixes:
            parts.append(f"Fixed: {'; '.join(fixes)}.")
        if checked.warnings:
            parts.append(f"{len(checked.warnings)} warning{'s' if len(checked.warnings) > 1 else ''} left.")
        return " ".join(parts)

    def _repeated_fix(self, before: str, after: str) -> str | None:
        """Counts small wording swaps made by hand, across all of the brand's campaigns. The second time one is
        seen, offers to remember it, unless memory already says so."""
        old_words, new_words = before.split(), after.split()
        offer = None
        counts = dict(self.campaign.hand_fixes)
        matcher = difflib.SequenceMatcher(a=old_words, b=new_words, autojunk=False)
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag != "replace" or i2 - i1 > 3 or j2 - j1 > 3:
                continue
            old, new = _bare(" ".join(old_words[i1:i2])), _bare(" ".join(new_words[j1:j2]))
            if not old or not new or old.lower() == new.lower():
                continue
            key = f"{old} → {new}"
            counts[key] = counts.get(key, 0) + 1
            elsewhere = self.session.scalar(
                select(func.coalesce(func.sum(Campaign.hand_fixes[key].as_integer()), 0))
                .where(Campaign.brand_id == self.brand.id, Campaign.id != self.campaign.id))
            suggestion = f"Use “{new}” instead of “{old}”."
            known = any(normalize(text) == normalize(suggestion) for text in core_texts(self.session, self.brand.id))
            if counts[key] + elsewhere == REPEATED_FIX and not known:
                offer = suggestion
        self.campaign.hand_fixes = counts
        self.session.commit()
        return offer


def not_checked(error: Exception) -> dict[str, str]:
    return {"check": "not checked", "quote": "", "problem": f"The checks couldn't run ({error}). Press Check again."}


def _bare(words: str) -> str:
    return words.strip(" .,;:!?\"'()“”‘’")
