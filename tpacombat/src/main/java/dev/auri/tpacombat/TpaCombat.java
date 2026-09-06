package dev.auri.tpacombat;

import net.fabricmc.api.DedicatedServerModInitializer;
import net.fabricmc.loader.api.FabricLoader;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import net.fabricmc.fabric.api.command.v2.CommandRegistrationCallback;
import net.fabricmc.fabric.api.entity.event.v1.ServerLivingEntityEvents;
import net.fabricmc.fabric.api.event.lifecycle.v1.ServerLifecycleEvents;
import net.fabricmc.fabric.api.event.lifecycle.v1.ServerTickEvents;
import net.fabricmc.fabric.api.networking.v1.ServerPlayConnectionEvents;

public final class TpaCombat implements DedicatedServerModInitializer {

    public static final String MOD_ID = "tpacombat";

    private static final Logger LOGGER = LoggerFactory.getLogger("tpacombat");

    private static volatile SocialManager socialManager;

    /** Read by the friends dialog, which is built from a static context. */
    public static SocialManager social() {
        return socialManager;
    }

    @Override
    public void onInitializeServer() {
        Config.load();

        PlayerDataStore store = new PlayerDataStore();
        SocialManager social = new SocialManager(store);
        socialManager = social;
        PlayerEffects effects = new PlayerEffects(store);
        PlaytimeTracker playtime = new PlaytimeTracker(store);

        PacketFilter.init(store);
        PearlSettings.init(store);
        PhantomTargeting.init(store);
        Messages.setStore(store);

        CombatManager combat = new CombatManager();
        combat.setStore(store);

        // Both mods now hook the same seam, so whichever runs second would find an already dead
        // player and skip. Deferring keeps that deterministic rather than order-dependent, and is
        // only reached if CombatLogger is actually installed alongside this mod.
        boolean externalCombatLogger = FabricLoader.getInstance().isModLoaded("combatlogger");
        combat.setDeferPunishment(externalCombatLogger);
        if (externalCombatLogger) {
            LOGGER.info("CombatLogger is installed, so it keeps combat-log punishment. "
                    + "Remove it to let this mod handle combat logging instead.");
        }
        TpaManager tpa = new TpaManager(combat);
        TpaCommands commands = new TpaCommands(tpa, combat, store, social);
        SettingsCommands settingsCommands = new SettingsCommands(store, effects);
        SocialCommands socialCommands = new SocialCommands(social, store);
        TabList tabList = new TabList();

        ServerLifecycleEvents.SERVER_STARTING.register(server -> {
            combat.onServerStarting();
            tabList.reset();
        });
        ServerLifecycleEvents.SERVER_STARTED.register(server -> {
            tpa.blocks().load(server);
            store.load(server);
        });

        // Registered before players are disconnected, so a restart is never punished as a combat log.
        ServerLifecycleEvents.SERVER_STOPPING.register(server -> {
            playtime.onServerStopping(server);
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
            effects.onEndTick(server);
            playtime.onEndTick(server);
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
            playtime.onJoin(handler.getPlayer());
        });

        // Leave handling runs from PlayerManager.remove instead of the DISCONNECT event; see
        // DisconnectHandler for why that event is the wrong place for it.
        DisconnectHandler.init(combat, tpa, playtime);

        CommandRegistrationCallback.EVENT.register((dispatcher, registryAccess, environment) -> {
            commands.register(dispatcher);
            settingsCommands.register(dispatcher);
            socialCommands.register(dispatcher);
            new PlaytimeCommand(playtime).register(dispatcher);
        });
    }
}
