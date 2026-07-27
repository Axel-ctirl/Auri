package dev.auri.combat.tpa;

import dev.auri.combat.AuriCombatPlugin;
import org.bukkit.entity.Player;
import org.bukkit.event.EventHandler;
import org.bukkit.event.EventPriority;
import org.bukkit.event.Listener;
import org.bukkit.event.entity.EntityDamageEvent;
import org.bukkit.event.inventory.InventoryClickEvent;
import org.bukkit.event.inventory.InventoryDragEvent;
import org.bukkit.event.player.PlayerMoveEvent;
import org.bukkit.event.player.PlayerQuitEvent;

/** Cancels in-flight teleports, drives the request GUI, and cleans up on disconnect. */
public final class TpaListener implements Listener {

    private final AuriCombatPlugin plugin;
    private final TpaManager tpa;

    public TpaListener(AuriCombatPlugin plugin, TpaManager tpa) {
        this.plugin = plugin;
        this.tpa = tpa;
    }

    @EventHandler(priority = EventPriority.MONITOR, ignoreCancelled = true)
    public void onMove(PlayerMoveEvent event) {
        if (!plugin.config().tpa().cancelOnMove() || !tpa.hasWarmup(event.getPlayer().getUniqueId())) {
            return;
        }
        // Looking around is fine — only leaving the block cancels.
        if (tpa.movedFromWarmupStart(event.getPlayer(), event.getTo())) {
            tpa.cancelWarmup(event.getPlayer().getUniqueId(), "tpa.warmup-cancelled-move");
        }
    }

    @EventHandler(priority = EventPriority.MONITOR, ignoreCancelled = true)
    public void onDamage(EntityDamageEvent event) {
        if (!plugin.config().tpa().cancelOnDamage() || !(event.getEntity() instanceof Player player)) {
            return;
        }
        if (tpa.hasWarmup(player.getUniqueId())) {
            tpa.cancelWarmup(player.getUniqueId(), "tpa.warmup-cancelled-damage");
        }
    }

    @EventHandler
    public void onQuit(PlayerQuitEvent event) {
        tpa.handleQuit(event.getPlayer());
    }

    @EventHandler
    public void onClick(InventoryClickEvent event) {
        if (!(event.getInventory().getHolder() instanceof TpaGui.Holder holder)) {
            return;
        }
        event.setCancelled(true);
        if (!(event.getWhoClicked() instanceof Player player)
                || !event.getInventory().equals(event.getClickedInventory())) {
            return;
        }

        // Re-resolve against live state: the request may have expired or been cancelled
        // between the popup opening and the click landing.
        if (tpa.findExact(holder.request()).isEmpty()) {
            player.closeInventory();
            plugin.messages().send(player, "errors.no-pending");
            return;
        }

        String senderName = plugin.getServer().getOfflinePlayer(holder.request().sender()).getName();
        switch (event.getRawSlot()) {
            case TpaGui.SLOT_ACCEPT -> {
                player.closeInventory();
                tpa.accept(player, senderName);
            }
            case TpaGui.SLOT_DENY -> {
                player.closeInventory();
                tpa.deny(player, senderName);
            }
            default -> {
                // Filler and the head aren't buttons.
            }
        }
    }

    @EventHandler
    public void onDrag(InventoryDragEvent event) {
        if (event.getInventory().getHolder() instanceof TpaGui.Holder) {
            event.setCancelled(true);
        }
    }
}
