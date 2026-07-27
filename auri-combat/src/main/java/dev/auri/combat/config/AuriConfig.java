package dev.auri.combat.config;

import org.bukkit.configuration.file.FileConfiguration;

import java.util.List;
import java.util.Locale;

/** Typed snapshot of config.yml. Rebuilt wholesale on reload so nothing reads a half-updated view. */
public final class AuriConfig {

    private final Combat combat;
    private final Tpa tpa;

    private AuriConfig(Combat combat, Tpa tpa) {
        this.combat = combat;
        this.tpa = tpa;
    }

    public static AuriConfig from(FileConfiguration c) {
        Combat combat = new Combat(
                Math.max(1, c.getInt("combat.duration", 20)),
                c.getBoolean("combat.triggers.melee", true),
                c.getBoolean("combat.triggers.projectiles", true),
                c.getBoolean("combat.triggers.explosions", true),
                c.getBoolean("combat.triggers.tamed-pets", true),
                c.getBoolean("combat.triggers.ender-pearl-land", false),
                c.getBoolean("combat.punish-on-quit.enabled", true),
                c.getBoolean("combat.punish-on-quit.drop-inventory", true),
                c.getBoolean("combat.punish-on-quit.clear-inventory", true),
                c.getBoolean("combat.punish-on-quit.broadcast", true),
                c.getBoolean("combat.restrict.elytra", true),
                c.getBoolean("combat.restrict.riptide", true),
                c.getBoolean("combat.restrict.ender-pearl", false),
                c.getBoolean("combat.restrict.totem", false),
                c.getBoolean("combat.command-blocker.enabled", true),
                c.getBoolean("combat.command-blocker.bypass-colons", true),
                c.getBoolean("combat.command-blocker.match-entire-words", true),
                c.getStringList("combat.command-blocker.blocked").stream()
                        .map(s -> s.toLowerCase(Locale.ROOT).trim())
                        .map(s -> s.startsWith("/") ? s.substring(1) : s)
                        .filter(s -> !s.isEmpty())
                        .toList());

        Tpa tpa = new Tpa(
                Math.max(1, c.getInt("tpa.request-expire", 60)),
                Math.max(0, c.getInt("tpa.warmup", 3)),
                Math.max(0, c.getInt("tpa.cooldown", 10)),
                c.getBoolean("tpa.cancel-on-move", true),
                c.getBoolean("tpa.cancel-on-damage", true),
                c.getBoolean("tpa.queue-requests", true),
                c.getBoolean("tpa.safe-teleport.enabled", true),
                Math.max(0, c.getInt("tpa.safe-teleport.search-radius", 5)),
                Math.max(0, c.getInt("tpa.safe-teleport.search-vertical", 5)),
                c.getBoolean("tpa.safe-teleport.fallback-to-original", false),
                c.getBoolean("tpa.gui.enabled", true),
                c.getString("tpa.gui.title", "<dark_gray>TPA REQUEST"),
                c.getString("tpa.gui.title-here", "<dark_gray>TPA HERE"),
                c.getBoolean("tpa.gui.close-on-expire", true));

        return new AuriConfig(combat, tpa);
    }

    public Combat combat() {
        return combat;
    }

    public Tpa tpa() {
        return tpa;
    }

    public record Combat(int duration,
                         boolean melee,
                         boolean projectiles,
                         boolean explosions,
                         boolean tamedPets,
                         boolean enderPearlLand,
                         boolean punishOnQuit,
                         boolean dropInventory,
                         boolean clearInventory,
                         boolean broadcastLog,
                         boolean restrictElytra,
                         boolean restrictRiptide,
                         boolean restrictEnderPearl,
                         boolean restrictTotem,
                         boolean blockerEnabled,
                         boolean bypassColons,
                         boolean matchEntireWords,
                         List<String> blockedCommands) {
    }

    public record Tpa(int requestExpire,
                      int warmup,
                      int cooldown,
                      boolean cancelOnMove,
                      boolean cancelOnDamage,
                      boolean queueRequests,
                      boolean safeTeleport,
                      int safeSearchRadius,
                      int safeSearchVertical,
                      boolean fallbackToOriginal,
                      boolean guiEnabled,
                      String guiTitle,
                      String guiTitleHere,
                      boolean guiCloseOnExpire) {
    }
}
