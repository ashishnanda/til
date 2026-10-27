---
title: Jump back to the previous branch with git switch -
tags: [git, cli]
---

Just like `cd -` takes you back to the previous directory, `git switch -`
(or the older `git checkout -`) switches to the branch you were on before.

```sh
git switch feature/login
git switch main
git switch -        # back on feature/login
```

The `-` is shorthand for `@{-1}`, "the branch checked out one switch ago", so
it works anywhere Git expects a branch name:

```sh
git merge -         # merge the previous branch into the current one
git diff @{-1}      # compare against it
```
