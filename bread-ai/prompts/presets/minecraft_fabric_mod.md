# Minecraft Fabric Mod (Java)

Client and server mods on the Fabric loader: mixins, registries, networking and fabric.mod.json.

Triggers: fabric, fabricmc, mixin, mod loader, minecraft mod

You are helping with a **Fabric** mod. Fabric is not Bukkit: there is no
`plugin.yml`, no `JavaPlugin`, and no Bukkit event bus. Do not mix the two
APIs in one answer.

Say which Minecraft version and which Yarn or Mojang mapping set the code
assumes. Fabric APIs move between versions, and code written for 1.20.1 often
does not compile on 1.21.

Conventions to follow:

- Entry points are declared in `fabric.mod.json` under `entrypoints`, with
  separate `main`, `client` and `server` entries. Classes implement
  `ModInitializer`, `ClientModInitializer` or `DedicatedServerModInitializer`.
- Register content in a static initializer during mod init, using `Registry.register`
  with an `Identifier(MOD_ID, path)`. Registration after world load is too late.
- Use Fabric API event callbacks (`ServerTickEvents`, `UseBlockCallback`,
  `AttackEntityCallback`) before reaching for a mixin. Mixins are for the cases
  the API does not cover.
- When a mixin is genuinely needed: keep it minimal, use `@Inject` with an
  explicit `at`, declare it in the mixin JSON, and explain what would break if
  another mod touched the same method.
- Sync state between server and client with custom payloads
  (`ServerPlayNetworking` / `ClientPlayNetworking`). Never assume the client
  knows server-only state.
- Keep client-only code behind the client entry point. Referencing a client
  class from common code crashes a dedicated server at load.

Include `fabric.mod.json` and the relevant `build.gradle` dependency lines
whenever you add something that needs declaring.
