from __future__ import annotations

from myopenclaw.skills.registry import SkillRegistry


class TaskPlanner:
    def __init__(self, registry: SkillRegistry) -> None:
        self.registry = registry

    def choose_skill_with_trace(self, user_input: str) -> dict:
        skills = self.registry.load_skills()
        if not skills:
            raise RuntimeError("No skills found in skills/ directory")

        user_tokens = {token.lower() for token in user_input.split() if token.strip()}
        ranked: list[dict] = []

        for skill in skills:
            searchable = " ".join([skill.name, skill.description] + skill.inputs + skill.constraints).lower()
            tokens = set(searchable.split())
            overlap = len(user_tokens.intersection(tokens))
            explicit_mention = skill.name.lower() in user_input.lower()
            score = overlap + (3 if explicit_mention else 0)
            ranked.append(
                {
                    "skill": skill.name,
                    "score": score,
                    "overlap": overlap,
                    "explicit_mention": explicit_mention,
                }
            )

        ranked.sort(
            key=lambda item: (-int(item["score"]), -int(item["overlap"]), str(item["skill"]))
        )
        chosen = str(ranked[0]["skill"])

        top = ranked[0]["score"]
        second = ranked[1]["score"] if len(ranked) > 1 else ranked[0]["score"]
        if top <= 0:
            confidence = 0.2
        elif len(ranked) == 1:
            confidence = 1.0
        else:
            margin = (top - second) / max(1.0, float(top))
            confidence = min(1.0, 0.45 + 0.55 * margin)

        return {
            "chosen_skill": chosen,
            "confidence": round(float(confidence), 3),
            "candidate_count": len(ranked),
            "top_candidates": ranked[:5],
        }

    def choose_skill(self, user_input: str) -> str:
        decision = self.choose_skill_with_trace(user_input=user_input)
        return str(decision["chosen_skill"])
