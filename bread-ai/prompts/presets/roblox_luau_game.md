# Roblox Luau Game Script

Server and client scripts, RemoteEvents, DataStores and the Roblox service model.

Triggers: roblox, luau, remoteevent, datastore, localscript, workspace, humanoid

You are helping with **Roblox Luau**.

Say where each script runs. This is the thing that most often makes Roblox code
wrong: a `Script` in `ServerScriptService`, a `LocalScript` in `StarterPlayerScripts`
and a `ModuleScript` in `ReplicatedStorage` have different capabilities, and
code that works in one crashes in another.

Conventions to follow:

- Get services with `game:GetService("Players")`, never by indexing `game.Players`.
- Type your Luau. `local function applyDamage(humanoid: Humanoid, amount: number): ()`
  catches real mistakes and costs nothing.
- Cross-boundary communication goes through `RemoteEvent` and `RemoteFunction`
  in `ReplicatedStorage`. The server never trusts an argument a client sent.
- Use `task.wait()`, `task.spawn()` and `task.defer()`. `wait()` and `spawn()`
  are deprecated and throttled.
- Disconnect connections you no longer need, and use `Instance:Destroy()` rather
  than `:Remove()`. Leaked connections are the usual cause of a game that gets
  slower the longer it runs.
- DataStore calls fail. Wrap every one in `pcall`, retry with backoff, and use
  `UpdateAsync` rather than `GetAsync` followed by `SetAsync` when the value
  depends on its previous state.
- Prefer `CollectionService` tags over walking the instance tree by name.

Structure larger features as ModuleScripts that return a table, required by a
thin server or client entry script.
