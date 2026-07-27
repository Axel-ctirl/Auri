package dev.auri.combat.combat;

import dev.auri.combat.AuriCombatPlugin;
import dev.auri.combat.config.AuriConfig;
import org.bukkit.entity.Player;
import org.bukkit.event.EventHandler;
import org.bukkit.event.EventPriority;
import org.bukkit.event.Listener;
import org.bukkit.event.player.PlayerCommandPreprocessEvent;

import java.util.Locale;

/**
 * Blocks escape commands while a player is combat tagged.
 *
 * <p>Two settings exist because the naive implementation leaks both ways. Without
 * {@code bypass-colons}, {@code /essentials:home} walks straight past a {@code /home} entry.
 * Without {@code match-entire-words}, a {@code /warp} entry also eats {@code /warpstone}.
 */
public final class CommandBlocker implements Listener {

    private final AuriCombatPlugin plugin;
    private final CombatManager combat;

    public CommandBlocker(AuriCombatPlugin plugin, CombatManager combat) {
        this.plugin = plugin;
        this.combat = combat;
    }

    @EventHandler(priority = EventPriority.LOWEST, ignoreCancelled = true)
    public void onCommand(PlayerCommandPreprocessEvent event) {
        AuriConfig.Combat cfg = plugin.config().combat();
        if (!cfg.blockerEnabled() || cfg.blockedCommands().isEmpty()) {
            return;
        }
        Player player = event.getPlayer();
        if (!combat.isTagged(player) || player.hasPermission("auri.combat.bypass")) {
            return;
        }
        if (isBlocked(normalise(event.getMessage(), cfg.bypassColons()), cfg)) {
            event.setCancelled(true);
            plugin.messages().send(player, "combat.blocked-command");
        }
    }

    /** Strips the leading slash, lowercases, collapses whitespace, and optionally drops a namespace. */
    private String normalise(String raw, boolean bypassColons) {
        String message = raw.trim().toLowerCase(Locale.ROOT);
        if (message.startsWith("/")) {
            message = message.substring(1);
        }
        message = message.replaceAll("\\s+", " ");
        if (bypassColons) {
            int space = message.indexOf(' ');
            String label = space == -1 ? message : message.substring(0, space);
            String rest = space == -1 ? "" : message.substring(space);
            int colon = label.indexOf(':');
            if (colon != -1) {
                message = label.substring(colon + 1) + rest;
            }
        }
        return message;
    }

    private boolean isBlocked(String typed, AuriConfig.Combat cfg) {
        for (String blocked : cfg.blockedCommands()) {
            if (typed.equals(blocked)) {
                return true;
            }
            if (cfg.matchEntireWords()) {
                // "/warp spawn" must match on a word boundary: "/warp spawn extra" yes, "/warp spawn1" no.
                if (typed.startsWith(blocked + " ")) {
                    return true;
                }
            } else if (typed.startsWith(blocked)) {
                return true;
            }
        }
        return false;
    }
}
