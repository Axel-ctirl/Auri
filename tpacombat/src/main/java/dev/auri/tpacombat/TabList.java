package dev.auri.tpacombat;

import net.minecraft.network.packet.s2c.play.PlayerListHeaderS2CPacket;
import net.minecraft.server.MinecraftServer;
import net.minecraft.server.network.ServerPlayerEntity;
import net.minecraft.text.MutableText;
import net.minecraft.text.Text;
import net.minecraft.util.Formatting;

/**
 * Server name and player count above the tab list, command hints below it.
 *
 * <p>Header and footer are one packet, so the whole thing is resent at once. That only happens
 * when the player count actually changes, plus once for each player as they join.
 */
public final class TabList {

    private int tickCounter;
    private int lastPlayerCount = -1;

    public void onEndTick(MinecraftServer server) {
        Config.TabListSettings settings = Config.get().tablist;
        if (!settings.enabled) {
            return;
        }
        if (++tickCounter < settings.refreshTicks) {
            return;
        }
        tickCounter = 0;

        int count = server.getCurrentPlayerCount();
        if (count == lastPlayerCount) {
            return;
        }
        lastPlayerCount = count;
        sendToAll(server);
    }

    public void sendToAll(MinecraftServer server) {
        if (!Config.get().tablist.enabled) {
            return;
        }
        PlayerListHeaderS2CPacket packet = buildPacket(server.getCurrentPlayerCount());
        for (ServerPlayerEntity player : server.getPlayerManager().getPlayerList()) {
            player.networkHandler.sendPacket(packet);
        }
    }

    public void sendTo(ServerPlayerEntity player, MinecraftServer server) {
        if (!Config.get().tablist.enabled) {
            return;
        }
        player.networkHandler.sendPacket(buildPacket(server.getCurrentPlayerCount()));
    }

    private static PlayerListHeaderS2CPacket buildPacket(int playerCount) {
        Config.TabListSettings settings = Config.get().tablist;
        Formatting accent = parseColor(settings.accentColor, Formatting.RED);

        MutableText header = Text.empty()
                .append(Text.literal(settings.serverName).formatted(accent))
                .append(Text.literal("\n"))
                .append(Text.literal(playerCount + (playerCount == 1 ? " Player" : " Players"))
                        .formatted(Formatting.WHITE));

        MutableText footer = Text.empty();
        for (int i = 0; i < settings.commands.size(); i++) {
            if (i > 0) {
                footer.append(Text.literal(" ").formatted(Formatting.GRAY));
            }
            footer.append(Text.literal(settings.commands.get(i)).formatted(accent));
        }

        return new PlayerListHeaderS2CPacket(header, footer);
    }

    /** Falls back to the default rather than breaking the tab list on a typo in the config. */
    private static Formatting parseColor(String name, Formatting fallback) {
        if (name == null) {
            return fallback;
        }
        Formatting parsed = Formatting.byName(name.toLowerCase(java.util.Locale.ROOT));
        return parsed != null && parsed.isColor() ? parsed : fallback;
    }

    public void reset() {
        lastPlayerCount = -1;
        tickCounter = 0;
    }
}
