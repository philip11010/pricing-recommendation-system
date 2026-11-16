"use client";

/**
 * The thirty skill pills, under their four headings.
 *
 * One component rather than the same block in two forms, because the two
 * forms have to agree on more than a layout now: which heading follows the
 * field, which label each pill carries for that field, and what a pill sends
 * when it is ticked. Registration and adding a service both ask the same
 * question, so they ask it with the same component.
 *
 * What a pill sends is always the skill id, whatever it is called on screen.
 * The labels under the field-specific heading come from lib/work-skills.ts
 * and the rest come from /meta/options, exactly as before.
 */

import { useMemo } from "react";

import { PillCheckbox } from "@/components/form";
import type { Option } from "@/lib/api-types";
import { SKILL_GROUPS } from "@/lib/copy";
import { workSkillLabels } from "@/lib/work-skills";

export function SkillPills({
  field,
  skills,
  chosen,
  onToggle,
}: {
  /** The field the mentor has picked, or "" before they have picked one. */
  field: string;
  /** The skill list /meta/options published, with the API's own labels. */
  skills: Option[];
  /** The skill ids ticked right now. */
  chosen: string[];
  onToggle: (id: string, on: boolean) => void;
}) {
  const apiLabels = useMemo(() => {
    const labels = new Map<string, string>();
    for (const skill of skills) {
      labels.set(skill.id, skill.label);
    }
    return labels;
  }, [skills]);

  const forField = useMemo(() => workSkillLabels(field), [field]);

  return (
    <>
      {SKILL_GROUPS.map((group) => (
        <fieldset key={group.name} className="mt-5 min-w-0">
          <legend className="mb-2.5 text-overline uppercase text-ink-500">
            {group.name}
          </legend>
          <div className="flex flex-wrap gap-2">
            {group.skillIds
              .filter((id) => apiLabels.has(id))
              .map((id) => (
                <PillCheckbox
                  key={id}
                  // The field's own label where the heading has one, and the
                  // label the API sent otherwise. The fallback is what a
                  // mentor sees before they have picked a field, when there
                  // is no field to be specific about.
                  label={
                    (group.fieldSpecific ? forField.get(id) : undefined) ??
                    apiLabels.get(id) ??
                    id
                  }
                  checked={chosen.includes(id)}
                  onChange={(on) => onToggle(id, on)}
                />
              ))}
          </div>
        </fieldset>
      ))}
    </>
  );
}
