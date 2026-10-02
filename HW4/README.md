# HW4：分支 (Branch)、合併 (Merge)、Fork、Pull Request 實作紀錄

## 1. 連結對照

我的（共 3 個）：
- 母專案：https://github.com/feng-organization/my-test
- 分支：https://github.com/feng-organization/my-test/tree/developGitBranch
- 子專案（fork）：https://github.com/Chifeng-chiu/my-test

老師範例：
- 母專案：https://github.com/se-test-examples/git-examples/commits/main/
- 分支：https://github.com/se-test-examples/git-examples/commits/developGitBranch
- 子專案：https://github.com/ccckmit/git-examples/commits/main/

對應關係：
| 老師 | 我的 | 說明 |
|---|---|---|
| `se-test-examples/git-examples` | `feng-organization/my-test` | 母專案，private，不是 fork |
| `developGitBranch` | `developGitBranch` | 同名分支，放 `gitBranch.md` |
| `ccckmit/git-examples`（fork） | `Chifeng-chiu/my-test`（fork） | `isFork=true`，parent 指回母專案 |
| `ccckmitFork.md` | `Chifeng-chiuFork.md` | fork 端新增的證明檔 |
| `Merge PR #1 from ccckmit/main (0810c21)` | `Merge PR #1 from developGitBranch (29eb839)` | 見下方差異說明 |

## 2. 分支（Branch）——做了什麼

目標：從 `main` 開出 `developGitBranch`，加一個 `gitBranch.md`。

實際下過的指令（在 `HW4/my-test` 這個 clone 裡）：

```powershell
git clone git@github.com:feng-organization/my-test.git
cd my-test
git branch developGitBranch
git checkout developGitBranch
# 新增檔案
"..." > gitBranch.md
git add gitBranch.md
git commit -m "add gitBranch.md"
git push -u origin developGitBranch
```

結果（已驗證）：
- `gh api repos/feng-organization/my-test/branches` 回傳 `main`、`developGitBranch`
- `developGitBranch` 上的 commit：`343fc98 add gitBranch.md`
- 母專案 `main` 的起點：`c43d9b3 Initial commit`
- 網頁：https://github.com/feng-organization/my-test/tree/developGitBranch 看得到 `gitBranch.md`

老師那邊對應的是 `0a6446a add gitBranch.md` 在 `developGitBranch` 上，做法相同。

## 3. 合併（Merge）+ Pull Request（PR）——做了什麼

我實際做的是「同 repo 內 PR」：

```powershell
# 法一：GitHub 網頁
# feng-organization/my-test > Pull requests > New > base:main <- compare:developGitBranch
# 標題 "add gitBranch.md" > Create > Merge pull request > Confirm
```

或 CLI 等價：

```powershell
gh pr create --repo feng-organization/my-test --base main --head developGitBranch --title "add gitBranch.md" --body ""
gh pr merge 1 --repo feng-organization/my-test --merge
```

結果（已驗證）：
- PR：https://github.com/feng-organization/my-test/pull/1
  `title="add gitBranch.md", head=developGitBranch, base=main, mergedAt=2026-10-02T02:41:36Z`
- `main` 歷史：`c43d9b3 Initial commit` → `343fc98 add gitBranch.md` → `29eb839 Merge pull request #1 from feng-organization/developGitBranch`
- 查 PR 內容：`gh pr view 1 --repo feng-organization/my-test --json files` 只有一個新增檔 `gitBranch.md`

和老師的差異（老實寫出來）：
- 老師的 `main` 是 `246dfa1 Initial` → `0a6446a add gitBranch.md` → `81314c1 add ccckmitFork.md` → `0810c21 Merge pull request #1 from ccckmit/main`。
- 也就是老師的 PR #1 是「從 fork（`ccckmit/main`）發回母專案」，我的 PR #1 是「從同 repo 的 `developGitBranch` 發回 `main`」。
- 要 100% 跟老師一樣，我還要把下一節的 `Chifeng-chiuFork.md` 推上去後，再從 `Chifeng-chiu/my-test` 發一次 cross-fork PR 回 `feng-organization/my-test`。

純 `git merge` 的本地等價（這次沒用，僅備註）：

```powershell
git checkout main
git merge developGitBranch
```

## 4. Fork——做了什麼（含踩雷）

一開始按 `Fork` 沒反應，查到原因是 Org 擋掉 private fork：

```powershell
gh api orgs/feng-organization --jq '.members_can_fork_private_repositories'
# false
```

解法（我是 org admin，直接用 API 開掉，等於網頁 `Org Settings > Member privileges > Repository forking` 打勾）：

```powershell
gh api -X PATCH orgs/feng-organization -f members_can_fork_private_repositories=true
gh api orgs/feng-organization --jq '.members_can_fork_private_repositories'
# true
```

然後在網頁：https://github.com/feng-organization/my-test 右上 `Fork > Create fork > Owner 選 Chifeng-chiu`。

結果（已驗證）：

```powershell
gh repo view Chifeng-chiu/my-test --json nameWithOwner,isFork,parent --jq .
# isFork=true, parent=feng-organization/my-test
```

這點和老師的 `ccckmit/git-examples (fork=true, parent=se-test-examples/git-examples)` 完全對應。

注意：GitHub 不允許 fork 回同一個 org，只能選個人帳號或另一個 org。

## 5. Fork 端的 commit（對應老師的 `ccckmitFork.md`）

老師 fork 端多了一個 `81314c1 add ccckmitFork.md`，我的對應檔是 `Chifeng-chiuFork.md`。

我本地已經做了，但還沒推上去（寫這份 README 當下狀態）：

```powershell
# 在 HW4/my-test（origin = feng-organization/my-test）上
New-Item Chifeng-chiuFork.md
git add Chifeng-chiuFork.md
git commit -m "add Chifeng-chiuFork.md"
# SHA: 38eecee，git log --all --graph 可見它從 c43d9b3 分出去，和 origin/main (29eb839) 呈 diverged
git status
# Your branch and 'origin/main' have diverged
```

要收尾的話，照老師流程應執行：

```powershell
git pull --rebase origin main
git push origin main
# 之後想做 cross-fork PR：先把 fork repo 同步，再
# Chifeng-chiu/my-test > Contribute > Open pull request > base: feng-organization/main
```

## 6. 附註：目錄裡多出來的 `HW4/my-test/my-test/`

`HW4/my-test/` 本身就是一個獨立 git repo（`origin=feng-organization/my-test`），裡面又多了一個 `HW4/my-test/my-test/` 二次 clone（含 `.git`、`gitBranch.md` 內容為 `#gut branch`  typo 版）。那是我測試時誤建的，不屬於作業，不會一起推到 `_se`（本次只加 `HW4/README.md`）。
