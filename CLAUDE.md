# Project instructions

- Experiment method: follow `experiments/README.md`. Before any run
  (controls and follow-ups too) the experiment file has aim, current
  state, variables, H0/H1 with an outcome table, and stop rules, and
  Sai has given an explicit go. Command step 0 is a smoke test that
  reproduces a stored number. Tag every reported number with its
  conditions. Record plan changes under "Deviations from plan"; never
  edit the H0/H1, outcome table or stop rules after the run.

- File deletion: use plain `rm`, not `/bin/rm` or `/usr/bin/rm`. Plain `rm` is
  aliased in this shell to `trash`, which moves files to the Trash instead of
  permanently deleting them — that's the intended behavior, don't bypass it.
  `trash` doesn't accept `-f`/`-r`/`-rf` flags (usage: `trash [-h][-s][-v]
  fileToMoveToTrash...`) — just call `rm <path>` with no flags, for files and
  directories alike.

- A PostToolUse hook (`.claude/hooks/ruff_clean.sh`) runs `ruff format` +
  `ruff check` after every Edit/Write/MultiEdit on a `.py` file, and reports
  failures back automatically. That's a correctness net, not a scratch pad —
  when a multi-step edit will leave a file in a known-broken intermediate
  state (references to a name not defined yet, a removal that isn't finished
  across the file), work it out fully — read the whole affected region, plan
  every touched spot — before making the edit that triggers the hook. Land
  the edit once the file is actually meant to be correct, not edit-by-edit
  while still mid-removal. Don't spend an edit-call turnaround finding out
  what ruff already would have told you from reading the file.
