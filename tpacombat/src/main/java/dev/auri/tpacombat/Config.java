package dev.auri.tpacombat;

import com.google.gson.Gson;
import com.google.gson.GsonBuilder;
import net.fabricmc.loader.api.FabricLoader;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.io.IOException;
import java.io.Reader;
import java.io.Writer;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;

/**
 * Mirrors the ForgeConfigSpec of the original mod, but backed by a plain JSON file since
 * Fabric ships no config framework. Key names and defaults are deliberately unchanged so an
 * existing tpacombat-common.toml maps across one-for-one.
 */
public final class Config {

    private static final Logger LOGGER = LoggerFactory.getLogger("tpacombat");
    private static final Gson GSON = new GsonBuilder().setPrettyPrinting().create();

    public Combat combat = new Combat();
    public Tpa tpa = new Tpa();
    public TabListSettings tablist = new TabListSettings();

    public static final class Combat {
        /** Seconds a player stays combat-tagged after the last PvP hit dealt or received. */
        public int tagSeconds = 20;
        /**
         * Kill players who disconnect while combat-tagged (drops inventory, normal death).
         * Kill credit goes to the last player who hit them. Disconnects caused by a
         * server stop/restart are never punished.
         */
        public boolean punishCombatLog = true;
        /** Announce combat-log deaths to the whole server. */
        public boolean broadcastCombatLog = true;
        /** Killing the player you were fighting clears your combat tag immediately. */
        public boolean untagOnKill = true;
    }

    public static final class Tpa {
        /** Seconds before a pending teleport request expires. */
        public int requestTimeoutSeconds = 60;
        /** Countdown after /tpaccept before the requester actually teleports. 0 = instant. */
        public int teleportDelaySeconds = 5;
        /** Cancel the countdown if the requester walks to another block. */
        public boolean cancelOnMove = true;
        /**
         * Cooldown before a player can send a new /tpa after their teleport was
         * cancelled by their own fault (moving or entering combat). 0 = no cooldown.
         */
        public int cancelCooldownSeconds = 15;
    }

    public static final class TabListSettings {
        /** Show the server name, player count and command hints on the tab list. */
        public boolean enabled = true;
        /** First header line, shown bold in the accent colour. */
        public String serverName = "Exploit SMP";
        /** Command hints listed in the footer. */
        public List<String> commands = new ArrayList<>(List.of("/gotorift", "/maces", "/tps"));
        /** Named Minecraft colour for the server name and the footer. */
        public String accentColor = "red";
        /** How often to check whether the player count changed, in ticks. 20 = once a second. */
        public int refreshTicks = 20;
    }

    private static volatile Config instance = new Config();

    public static Config get() {
        return instance;
    }

    private static Path path() {
        return FabricLoader.getInstance().getConfigDir().resolve("tpacombat.json");
    }

    public static void load() {
        Path path = path();
        if (!Files.exists(path)) {
            instance = new Config();
            save();
            return;
        }
        try (Reader reader = Files.newBufferedReader(path)) {
            Config loaded = GSON.fromJson(reader, Config.class);
            if (loaded == null) {
                loaded = new Config();
            }
            if (loaded.combat == null) {
                loaded.combat = new Combat();
            }
            if (loaded.tpa == null) {
                loaded.tpa = new Tpa();
            }
            if (loaded.tablist == null) {
                loaded.tablist = new TabListSettings();
            }
            if (loaded.tablist.commands == null) {
                loaded.tablist.commands = new ArrayList<>();
            }
            loaded.clamp();
            instance = loaded;
        } catch (Exception e) {
            LOGGER.error("Failed to read {}, keeping defaults", path, e);
            instance = new Config();
        }
        save();
    }

    public static void save() {
        Path path = path();
        try {
            Files.createDirectories(path.getParent());
            try (Writer writer = Files.newBufferedWriter(path)) {
                GSON.toJson(instance, writer);
            }
        } catch (IOException e) {
            LOGGER.error("Failed to write {}", path, e);
        }
    }

    /** Reproduces the bounds the Forge defineInRange calls enforced. */
    private void clamp() {
        combat.tagSeconds = clamp(combat.tagSeconds, 1, 3600);
        tpa.requestTimeoutSeconds = clamp(tpa.requestTimeoutSeconds, 1, 3600);
        tpa.teleportDelaySeconds = clamp(tpa.teleportDelaySeconds, 0, 3600);
        tpa.cancelCooldownSeconds = clamp(tpa.cancelCooldownSeconds, 0, 3600);
        tablist.refreshTicks = clamp(tablist.refreshTicks, 1, 1200);
    }

    private static int clamp(int value, int min, int max) {
        return Math.max(min, Math.min(max, value));
    }
}
