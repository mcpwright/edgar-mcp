---
description: Adversarially review the current branch's diff with the code-reviewer subagent (fresh context) before opening a PR.
argument-hint: "[base ref — defaults to main]"
---

Run a pre-PR code review of the current branch using the **`code-reviewer`**
subagent. The point is a review in a *fresh context* — so do **not** summarize the
diff yourself; let the subagent read the code.

Base ref: `$1` (default `main` if empty).

1. Sanity-check the range: run `git log <base>..HEAD --oneline` and
   `git diff --stat <base>...HEAD` so you (and I) can see what's in scope. If the
   branch is `main` or has no commits over the base, stop and say so.
2. Launch the **`code-reviewer`** subagent (Task tool, `subagent_type:
   code-reviewer`). Tell it only the base ref and that it should run
   `git diff <base>...HEAD` and read the touched files itself. Do not paste the
   diff or describe the change — its value is the independent read.
3. Relay the subagent's report back **verbatim** under a `## Code review` heading.
4. **Do not fix anything yet.** Wait for me to decide which findings to address;
   then I'll have you fold them in before the PR.
