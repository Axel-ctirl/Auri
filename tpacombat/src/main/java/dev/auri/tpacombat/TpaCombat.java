package dev.auri.tpacombat;

import net.fabricmc.api.DedicatedServerModInitializer;
import net.fabricmc.fabric.api.command.v2.CommandRegistrationCallback;
import net.fabricmc.fabric.api.entity.event.v1.ServerLivingEntityEvents;
import net.fabricmc.fabric.api.event.lifecycle.v1.ServerLifecycleEvents;
import net.fabricmc.fabric.api.event.lifecycle.v1.ServerTickEvents;
import net.fabricmc.fabric.api.networking.v1.ServerPlayConnectionEvents;

public final class TpaCombat implements DedicatedServerModInitializer {

    public static final String MOD_ID = "tpacombat";

    @Override
    public void onInitializeServer() {
        Config.load();

        PlayerDataStore store = new PlayerDataStore();
        SocialManager social = new SocialManager(store);
        PacketFilter.init(store);
        Messages.setStore(store);

        CombatManager combat = new CombatManager();
        combat.setStore(store);
        TpaManager tpa = new TpaManager(combat);
        TpaCommands commands = new TpaCommands(tpa, combat, store, social);
        SettingsCommands settingsCommands = new SettingsCommands(store);
        SocialCommands socialCommands = new SocialCommands(social, store);
        TabList tabList = new TabList();

        ServerLifecycleEvents.SERVER_STARTING.register(server -> {
            Config.load();
            combat.onServerStarting();
            tabList.reset();
        });
        ServerLifecycleEvents.SERVER_STARTED.register(server -> {
            tpa.blocks().load(server);
            store.load(server);
        });

        // Registered before players are disconnected, so a restart is never punished as a combat log.
        ServerLifecycleEvents.SERVER_STOPPING.register(server -> {
            combat.onServerStopping();
            tpa.blocks().save();
            store.save();
        });

        // Flushes accumulated setting/follow changes about once a minute instead of per click.
        int[] saveTimer = {0};
        ServerTickEvents.END_SERVER_TICK.register(server -> {
            combat.onEndTick(server);
            tpa.onEndTick(server);
            tabList.onEndTick(server);
            if (++saveTimer[0] >= 1200) {
                saveTimer[0] = 0;
                store.saveIfDirty();
            }
        });

        ServerLivingEntityEvents.AFTER_DAMAGE.register(
                (entity, source, baseDamage, damageTaken, blocked) -> combat.onAfterDamage(entity, source));
        ServerLivingEntityEvents.AFTER_DEATH.register(combat::onAfterDeath);

        ServerPlayConnectionEvents.JOIN.register((handler, sender, server) -> {
            tabList.sendTo(handler.getPlayer(), server);
            // Keep the stored name current so offline follow lists stay readable.
            store.get(handler.getPlayer().getUuid()).lastKnownName =
                    handler.getPlayer().getGameProfile().name();
            store.markDirty();
        });

        ServerPlayConnectionEvents.DISCONNECT.register((handler, server) -> {
            combat.onDisconnect(handler.getPlayer());
            tpa.onDisconnect(handler.getPlayer());
        });

        CommandRegistrationCallback.EVENT.register((dispatcher, registryAccess, environment) -> {
            commands.register(dispatcher);
            settingsCommands.register(dispatcher);
            socialCommands.register(dispatcher);
        });
    }
}
