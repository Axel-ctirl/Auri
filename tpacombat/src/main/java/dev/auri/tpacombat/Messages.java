package dev.auri.tpacombat;

import net.minecraft.server.MinecraftServer;
import net.minecraft.server.network.ServerPlayerEntity;
import net.minecraft.text.ClickEvent;
import net.minecraft.text.HoverEvent;
import net.minecraft.text.MutableText;
import net.minecraft.text.Text;
import net.minecraft.util.Formatting;

public final class Messages {

    private Messages() {
    }

    public static void chat(ServerPlayerEntity to, Text message) {
        to.sendMessage(message);
    }

    public static void actionBar(ServerPlayerEntity to, Text message) {
        to.sendMessage(message, true);
    }

    private static PlayerDataStore store;

    public static void setStore(PlayerDataStore dataStore) {
        store = dataStore;
    }

    /** Sent per player rather than server-wide so the "Server Messages" toggle can opt out. */
    public static void broadcast(MinecraftServer server, Text message) {
        Text prefixed = withPrefix(message);
        for (ServerPlayerEntity player : server.getPlayerManager().getPlayerList()) {
            if (store == null || store.peek(player.getUuid()).serverMessages) {
                player.sendMessage(prefixed);
            }
        }
    }

    private static Text c(String text, Formatting color) {
        return Text.literal(text).formatted(color);
    }

    private static MutableText seq(Text... parts) {
        MutableText out = Text.empty();
        for (Text part : parts) {
            out.append(part);
        }
        return out;
    }

    public static Text withPrefix(Text message) {
        return seq(c("[", Formatting.GRAY), c("TPA", Formatting.GOLD), c("] ", Formatting.GRAY), message);
    }

    public static Text playerNotFound(String player) {
        return seq(c("Player ", Formatting.RED), c(player, Formatting.WHITE), c(" is not online.", Formatting.RED));
    }

    public static Text inCombat(int seconds) {
        return seq(c("You are in combat! You can't do that for another ", Formatting.RED),
                c(seconds + "s", Formatting.WHITE), c(".", Formatting.RED));
    }

    public static Text combatBar(int seconds) {
        return seq(c("In combat: ", Formatting.RED), c(seconds + "s", Formatting.WHITE),
                c(" - do not log out!", Formatting.RED));
    }

    public static Text combatExpired() {
        return c("You are no longer in combat.", Formatting.GREEN);
    }

    public static Text combatUntagKill() {
        return c("Kill! You are no longer in combat.", Formatting.GREEN);
    }

    public static Text combatLogBroadcast(String player) {
        return seq(c(player, Formatting.WHITE), c(" combat-logged and paid the price!", Formatting.RED));
    }

    public static Text combatLogBroadcastKiller(String player, String killer) {
        return seq(c(player, Formatting.WHITE), c(" combat-logged while fighting ", Formatting.RED),
                c(killer, Formatting.WHITE), c(" and paid the price!", Formatting.RED));
    }

    public static Text tpaHereSent(String player, int seconds) {
        return seq(c("TPAHERE sent to ", Formatting.GREEN), c(player, Formatting.WHITE), c(" ", Formatting.GREEN),
                c("(expires in " + seconds + "s)", Formatting.GRAY));
    }

    public static Text tpaHereReceivedBar(String player) {
        return seq(c(player, Formatting.WHITE), c(" wants you to TP to them", Formatting.GOLD));
    }

    public static Text tpaHereReceived(String player, int seconds) {
        MutableText accept = Text.literal("[Accept]").styled(style -> style
                .withColor(Formatting.GREEN).withBold(Boolean.TRUE)
                .withClickEvent(new ClickEvent.RunCommand("/tpaccept")));
        MutableText deny = Text.literal("[Deny]").styled(style -> style
                .withColor(Formatting.RED).withBold(Boolean.TRUE)
                .withClickEvent(new ClickEvent.RunCommand("/tpdeny")));
        return seq(c(player, Formatting.WHITE), c(" wants you to TP to them. ", Formatting.GOLD), accept,
                c(" ", Formatting.GOLD), deny, c(" (" + seconds + "s)", Formatting.GRAY));
    }

    public static Text tpaAutoAccepted(String player) {
        return seq(c(player, Formatting.WHITE), c(" auto-accepted your request.", Formatting.GREEN));
    }

    public static Text tpaAutoAcceptedByYou(String player) {
        return seq(c("Auto-accepted ", Formatting.GREEN), c(player, Formatting.WHITE),
                c("'s request.", Formatting.GREEN));
    }

    public static Text autoAddSelf() {
        return c("You can't auto-accept yourself.", Formatting.RED);
    }

    public static Text autoAdded(String player) {
        return seq(c(player, Formatting.WHITE),
                c("'s teleport requests will now be accepted automatically.", Formatting.GREEN));
    }

    public static Text autoAlready(String player) {
        return seq(c(player, Formatting.WHITE), c(" is already auto-accepted.", Formatting.RED));
    }

    public static Text autoRemoved(String player) {
        return seq(c(player, Formatting.WHITE),
                c(" will be asked about again.", Formatting.YELLOW));
    }

    public static Text tpaSelf() {
        return c("You can't send a teleport request to yourself.", Formatting.RED);
    }

    public static Text tpaSent(String player, int seconds) {
        return seq(c("TPA sent to ", Formatting.GREEN), c(player, Formatting.WHITE), c(" ", Formatting.GREEN),
                c("(expires in " + seconds + "s)", Formatting.GRAY));
    }

    public static Text tpaReceivedBar(String player) {
        return seq(c(player, Formatting.WHITE), c(" wants to TP to you", Formatting.GOLD));
    }

    public static Text tpaBlockedByTarget(String player) {
        return seq(c(player, Formatting.WHITE), c(" has blocked TPA requests from you.", Formatting.RED));
    }

    public static Text tpaPrivacyBlocked(String player, Visibility visibility) {
        return seq(c(player, Formatting.WHITE), c(" " + visibility.deniedReason() + ".", Formatting.RED));
    }

    public static Text tpaAlreadyPending(String player) {
        return seq(c("You already have a pending request to ", Formatting.RED), c(player, Formatting.WHITE),
                c(".", Formatting.RED));
    }

    public static Text tpaNonePending() {
        return c("You have no pending teleport requests.", Formatting.RED);
    }

    public static Text tpaRequesterInCombat(String player) {
        return seq(c(player, Formatting.WHITE), c(" is in combat and can't teleport right now.", Formatting.RED));
    }

    public static Text tpaAcceptRequester(String player) {
        return seq(c(player, Formatting.WHITE), c(" accepted your TPA!", Formatting.GREEN));
    }

    public static Text tpaAcceptTarget(String player) {
        return seq(c("You accepted ", Formatting.GREEN), c(player, Formatting.WHITE), c("'s TPA.", Formatting.GREEN));
    }

    public static Text tpaWarmup(int seconds) {
        return seq(c("Teleporting in ", Formatting.GOLD), c(seconds + "s", Formatting.YELLOW));
    }

    public static Text tpaTeleported(String player) {
        return seq(c("Teleported to ", Formatting.GREEN), c(player, Formatting.WHITE), c(".", Formatting.GREEN));
    }

    public static Text tpaCancelledMoved() {
        return c("Teleport cancelled - you moved!", Formatting.RED);
    }

    public static Text tpaCancelledCombat() {
        return c("Teleport cancelled - you entered combat!", Formatting.RED);
    }

    public static Text tpaCancelledOffline(String player) {
        return seq(c("Teleport cancelled - ", Formatting.RED), c(player, Formatting.WHITE),
                c(" went offline.", Formatting.RED));
    }

    public static Text tpaCooldown(int seconds) {
        return seq(c("Wait ", Formatting.RED), c(seconds + "s", Formatting.WHITE),
                c(" before sending another TPA.", Formatting.RED));
    }

    public static Text tpaSelectHeader() {
        return c("Click a player to send them a teleport request:", Formatting.YELLOW);
    }

    public static Text tpaSelectNone() {
        return c("There are no other players online.", Formatting.RED);
    }

    public static Text tpaSelectEntry(String player) {
        return Text.literal("[" + player + "]").styled(style -> style
                .withColor(Formatting.GREEN)
                .withClickEvent(new ClickEvent.RunCommand("/tpa " + player))
                .withHoverEvent(new HoverEvent.ShowText(Text.literal("Send a teleport request to " + player))));
    }

    public static Text tpaDenyRequester(String player) {
        return seq(c(player, Formatting.WHITE), c(" denied your TPA.", Formatting.RED));
    }

    public static Text tpaDenyTarget(String player) {
        return seq(c("You denied ", Formatting.RED), c(player, Formatting.WHITE), c("'s TPA.", Formatting.RED));
    }

    public static Text tpaReceived(String player, int seconds) {
        MutableText accept = Text.literal("[Accept]").styled(style -> style
                .withColor(Formatting.GREEN)
                .withBold(Boolean.TRUE)
                .withClickEvent(new ClickEvent.RunCommand("/tpaccept")));
        MutableText deny = Text.literal("[Deny]").styled(style -> style
                .withColor(Formatting.RED)
                .withBold(Boolean.TRUE)
                .withClickEvent(new ClickEvent.RunCommand("/tpdeny")));
        return seq(c(player, Formatting.WHITE), c(" wants to TP to you. ", Formatting.GOLD), accept,
                c(" ", Formatting.GOLD), deny, c(" (" + seconds + "s)", Formatting.GRAY));
    }

    public static Text blockSelf() {
        return c("You can't block yourself.", Formatting.RED);
    }

    public static Text blockAdded(String player) {
        return seq(c(player, Formatting.WHITE), c(" can no longer send you teleport requests.", Formatting.GREEN));
    }

    public static Text blockAlready(String player) {
        return seq(c(player, Formatting.WHITE), c(" is already blocked.", Formatting.RED));
    }

    public static Text blockRemoved(String player) {
        return seq(c(player, Formatting.WHITE), c(" can send you teleport requests again.", Formatting.GREEN));
    }

    public static Text blockNotBlocked(String player) {
        return seq(c(player, Formatting.WHITE), c(" is not on your block list.", Formatting.RED));
    }

    public static Text blockListHeader(int count, String players) {
        return seq(c("Blocked players (", Formatting.YELLOW), c(String.valueOf(count), Formatting.WHITE),
                c("):", Formatting.YELLOW), c(" " + players, Formatting.WHITE));
    }

    public static Text blockListEmpty() {
        return c("You haven't blocked anyone.", Formatting.YELLOW);
    }
}
