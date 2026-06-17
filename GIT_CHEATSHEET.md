# 🪥 My Git Cheat Sheet

> Goal: make git feel automatic, like brushing teeth.
> Rhythm: **status → add → commit → push** (look, act, look).

---

## 🔁 THE DAILY LOOP (use this 95% of the time)

```bash
git status                  # 1. What changed? (look first, always)
git add .                   # 2. Put all changes in the "cart"
git commit -m "message"     # 3. Save a snapshot with a note
git push                    # 4. Send it up to GitHub
```

`push` = send UP to GitHub ⬆️   |   `pull` = bring DOWN from GitHub ⬇️

---

## 🌿 BRANCH WORKFLOW (the company way — never work directly on main)

```bash
git checkout -b my-feature        # create a branch + switch to it
# ... edit files ...
git add .
git commit -m "describe change"
git push -u origin my-feature     # push branch to GitHub
```
Then on GitHub: **Compare & pull request → Create PR → Merge PR → Delete branch.**

Back on your computer, sync main:
```bash
git checkout main
git pull                          # download the merged change
git branch -d my-feature          # delete the local branch (optional cleanup)
```

---

## 🧱 ONE-TIME SETUP (only for a brand-new project)

```bash
git init
git config --global user.name "SIDDHI"
git config --global user.email "siddhik355@gmail.com"
git add .
git commit -m "Initial commit"
git remote add origin <github-url>
git push -u origin main
```

---

## 🆘 HANDY RESCUE COMMANDS

```bash
git log --oneline           # see commit history (q to quit)
git branch                  # list branches (* = where I am)
git diff                    # see exactly what I changed (not yet added)
git checkout -- <file>      # undo unsaved changes to a file
git restore <file>          # same (newer syntax)
```

---

## 💡 REMEMBER
- `git add` is **silent** when it works. Use `git status` to SEE.
- `.gitignore` keeps secrets (`.env`) and junk out — never commit API keys.
- A commit is a **permanent save point**. You can always go back.
- `main` is sacred. Experiment on **branches**.
