# HW4：分支、合併、Fork、Pull Request 實作紀錄

## 連結

- 母專案：https://github.com/feng-organization/my-test/commits/main/
- 分支：https://github.com/feng-organization/my-test/commits/developGitBranch
- 子專案（fork）：https://github.com/Chifeng-chiu/my-test/commits/main/

## 1. 分支（Branch）

目標：從 `main` 開出 `developGitBranch`，加一個 `gitBranch.md`。

指令（在 `HW4/my-test` 這個 clone 裡）：

```powershell
git clone git@github.com:feng-organization/my-test.git
cd my-test
git branch developGitBranch
git checkout developGitBranch
"..." > gitBranch.md
git add gitBranch.md
git commit -m "add gitBranch.md"
git push -u origin developGitBranch
```

結果：
- `gh api repos/feng-organization/my-test/branches` 回傳 `main`、`developGitBranch`
- `developGitBranch` 上的 commit：`343fc98 add gitBranch.md`
- 母專案起點：`c43d9b3 Initial commit`
- 網頁：https://github.com/feng-organization/my-test/commits/developGitBranch 看得到 `gitBranch.md`

## 2. 合併（Merge）

這次是用 GitHub PR 方式合併（見下一節），本地等價指令僅備註：

```powershell
git checkout main
git merge developGitBranch
```

實際合併結果在 `main` 上：
`c43d9b3 Initial commit` → `343fc98 add gitBranch.md` → `29eb839 Merge pull request #1 from feng-organization/developGitBranch`

## 3. Fork

一開始按 `Fork` 沒反應，查到 Org 擋掉 private fork：

```powershell
gh api orgs/feng-organization --jq '.members_can_fork_private_repositories'
# false
```

我是 org admin，直接用 API 開掉（等於網頁 `Org Settings > Member privileges > Repository forking` 打勾）：

```powershell
gh api -X PATCH orgs/feng-organization -f members_can_fork_private_repositories=true
gh api orgs/feng-organization --jq '.members_can_fork_private_repositories'
# true
```

然後在網頁：https://github.com/feng-organization/my-test 右上 `Fork > Create fork > Owner 選 Chifeng-chiu`。

結果：

```powershell
gh repo view Chifeng-chiu/my-test --json nameWithOwner,isFork,parent --jq .
# isFork=true, parent=feng-organization/my-test
```

注意：GitHub 不允許 fork 回同一個 org，只能選個人帳號或另一個 org。

Fork 端的證明檔 `Chifeng-chiuFork.md` 本地已建（`38eecee add Chifeng-chiuFork.md`），目前和 `origin/main (29eb839)` 呈 diverged，還沒推：

```powershell
New-Item Chifeng-chiuFork.md
git add Chifeng-chiuFork.md
git commit -m "add Chifeng-chiuFork.md"
git pull --rebase origin main
git push origin main
```

## 4. Pull Request

做法（同 repo 內 PR）：

```powershell
# GitHub 網頁：
# feng-organization/my-test > Pull requests > New > base:main <- compare:developGitBranch
# 標題 "add gitBranch.md" > Create > Merge pull request > Confirm
```

或 CLI 等價：

```powershell
gh pr create --repo feng-organization/my-test --base main --head developGitBranch --title "add gitBranch.md" --body ""
gh pr merge 1 --repo feng-organization/my-test --merge
```

結果：
- PR：https://github.com/feng-organization/my-test/pull/1
  `title="add gitBranch.md", head=developGitBranch, base=main, mergedAt=2026-10-02T02:41:36Z`
- `gh pr view 1 --repo feng-organization/my-test --json files` 只有一個新增檔 `gitBranch.md`

後續可再從 `Chifeng-chiu/my-test` 發一次 cross-fork PR 回 `feng-organization/my-test`（`Contribute > Open pull request > base: feng-organization/main`）。

## 附註

`HW4/my-test/` 本身是獨立 git repo（`origin=feng-organization/my-test`），裡面多了一個 `HW4/my-test/my-test/` 二次 clone，是測試時誤建的，不屬於作業，本次只加 `HW4/README.md`。
