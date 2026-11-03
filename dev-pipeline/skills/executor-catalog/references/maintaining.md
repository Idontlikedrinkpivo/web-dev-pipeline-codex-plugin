# Changing the Codex catalog

Edit codex/models.json in the source build repository. role:<name> owns each
Codex role's model and effort; _stages owns recommended stage chat settings.
The generated plugin copy is models.json, agents/*.toml and this reference.
Changing a Claude alias mapping alone must not silently change an existing
explicit Codex role. New roles need their own entry and a dispatcher; keep
the model-policy tests green before release. Do not edit Claude agent model
fields to tune Codex. The shared catalog still defines packets and branches.

Rebuild and run the Codex compatibility tests. Release both distributions at
the same version, even for Codex-only tuning. Install the new plugin and run
install-agents.sh to refresh user roles. Check installed TOML files match the
release. Do not change global defaults, a running chat, or another user's
custom model configuration while merely reviewing the catalog.

When selecting a model, check availability and supported effort against the
host's actual model catalog. Request the user's model-selection choice when
required by the chat tool; never bypass it through a tool permission setting.
If the configured model cannot run, report the exact role/stage and blocker.

Keep rationale and measurements in model-economics.md. A re-point needs a
representative evaluation of accepted output, missed defects, rework, time
and observed usage; a renamed grade or more expensive model is not evidence.
