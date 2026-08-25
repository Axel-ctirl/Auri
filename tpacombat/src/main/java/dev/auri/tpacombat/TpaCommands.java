package dev.auri.tpacombat;

import com.mojang.brigadier.CommandDispatcher;
import com.mojang.brigadier.arguments.StringArgumentType;
import com.mojang.brigadier.context.CommandContext;
import com.mojang.brigadier.exceptions.CommandSyntaxException;
import com.mojang.brigadier.suggestion.SuggestionProvider;
import net.minecraft.command.CommandSource;
import net.minecraft.command.argument.EntityArgumentType;
import net.minecraft.command.argument.GameProfileArgumentType;
import net.minecraft.server.MinecraftServer;
import net.minecraft.server.PlayerConfigEntry;
import net.minecraft.server.command.CommandManager;
import net.minecraft.server.command.ServerCommandSource;
import net.minecraft.server.network.ServerPlayerEntity;
import net.minecraft.text.MutableText;
import net.minecraft.text.Text;

import java.util.Collection;
import java.util.List;
import java.util.Map;
import java.util.UUID;

public final class TpaCommands {

    private final TpaManager tpa;
    private final CombatManager combat;

    private static final SuggestionProvider<ServerCommandSource> ONLINE_PLAYERS =
            (context, builder) -> CommandSource.suggestMatching(context.getSource().getPlayerNames(), builder);

    public TpaCommands(TpaManager tpa, CombatManager combat) {
        this.tpa = tpa;
        this.combat = combat;
    }

    public void register(CommandDispatcher<ServerCommandSource> dispatcher) {
        dispatcher.register(CommandManager.literal("tpa")
                .executes(context -> quickSelect(context.getSource().getPlayerOrThrow()))
                .then(CommandManager.argument("player", EntityArgumentType.player())
                        .executes(context -> tpa(context.getSource().getPlayerOrThrow(),
                                EntityArgumentType.getPlayer(context, "player")))));

        dispatcher.register(CommandManager.literal("tpaccept")
                .executes(context -> tpaccept(context.getSource().getPlayerOrThrow())));

        dispatcher.register(CommandManager.literal("tpdeny")
                .executes(context -> tpdeny(context.getSource().getPlayerOrThrow())));

        dispatcher.register(CommandManager.literal("tpablock")
                .then(CommandManager.argument("player", GameProfileArgumentType.gameProfile())
                        .suggests(ONLINE_PLAYERS)
                        .executes(context -> tpablock(context.getSource().getPlayerOrThrow(),
                                GameProfileArgumentType.getProfileArgument(context, "player")))));

        dispatcher.register(CommandManager.literal("tpaunblock")
                .then(CommandManager.argument("player", StringArgumentType.word())
                        .suggests(this::suggestBlocked)
                        .executes(context -> tpaunblock(context.getSource().getPlayerOrThrow(),
                                StringArgumentType.getString(context, "player")))));

        dispatcher.register(CommandManager.literal("tpablocks")
                .executes(context -> tpablocks(context.getSource().getPlayerOrThrow())));
    }

    private java.util.concurrent.CompletableFuture<com.mojang.brigadier.suggestion.Suggestions> suggestBlocked(
            CommandContext<ServerCommandSource> context, com.mojang.brigadier.suggestion.SuggestionsBuilder builder) {
        ServerPlayerEntity owner = context.getSource().getPlayer();
        if (owner != null) {
            return CommandSource.suggestMatching(tpa.blocks().blocksOf(owner.getUuid()).values(), builder);
        }
        return builder.buildFuture();
    }

    private boolean denyIfInCombat(ServerPlayerEntity player) {
        if (combat.isTagged(player)) {
            combat.sendInCombat(player);
            return true;
        }
        return false;
    }

    /** Bare /tpa prints a clickable roster instead of erroring on a missing argument. */
    private int quickSelect(ServerPlayerEntity sender) {
        List<String> names = sender.getEntityWorld().getServer().getPlayerManager().getPlayerList().stream()
                .filter(p -> !p.getUuid().equals(sender.getUuid()))
                .map(p -> p.getGameProfile().name())
                .sorted(String.CASE_INSENSITIVE_ORDER)
                .toList();
        if (names.isEmpty()) {
            Messages.chat(sender, Messages.withPrefix(Messages.tpaSelectNone()));
            return 0;
        }
        Messages.chat(sender, Messages.withPrefix(Messages.tpaSelectHeader()));
        MutableText line = Text.empty();
        for (int i = 0; i < names.size(); i++) {
            if (i > 0) {
                line.append(Text.literal(" "));
            }
            line.append(Messages.tpaSelectEntry(names.get(i)));
        }
        Messages.chat(sender, line);
        return 1;
    }

    private int tpa(ServerPlayerEntity sender, ServerPlayerEntity target) {
        if (denyIfInCombat(sender)) {
            return 0;
        }
        int cooldown = tpa.cooldownRemaining(sender);
        if (cooldown > 0) {
            Messages.actionBar(sender, Messages.tpaCooldown(cooldown));
            return 0;
        }
        if (target.getUuid().equals(sender.getUuid())) {
            Messages.actionBar(sender, Messages.tpaSelf());
            return 0;
        }

        String targetName = target.getGameProfile().name();
        if (tpa.blocks().isBlocked(target.getUuid(), sender.getUuid())) {
            Messages.actionBar(sender, Messages.tpaBlockedByTarget(targetName));
            return 0;
        }
        if (tpa.hasPendingFrom(sender, target)) {
            Messages.actionBar(sender, Messages.tpaAlreadyPending(targetName));
            return 0;
        }

        tpa.addRequest(sender, target);
        int seconds = tpa.timeoutSeconds();
        String senderName = sender.getGameProfile().name();
        Messages.actionBar(sender, Messages.tpaSent(targetName, seconds));
        Messages.chat(target, Messages.withPrefix(Messages.tpaReceived(senderName, seconds)));
        Messages.actionBar(target, Messages.tpaReceivedBar(senderName));
        return 1;
    }

    private int tpaccept(ServerPlayerEntity target) {
        if (denyIfInCombat(target)) {
            return 0;
        }
        TpaManager.Request request = tpa.peekLatest(target);
        if (request == null) {
            Messages.actionBar(target, Messages.tpaNonePending());
            return 0;
        }
        ServerPlayerEntity requester = target.getEntityWorld().getServer()
                .getPlayerManager().getPlayer(request.requester());
        if (requester == null) {
            tpa.pollLatest(target);
            Messages.actionBar(target, Messages.tpaNonePending());
            return 0;
        }
        // Leave the request queued so the requester can still be accepted once they are out of combat.
        if (combat.isTagged(requester)) {
            Messages.actionBar(target, Messages.tpaRequesterInCombat(requester.getGameProfile().name()));
            combat.sendInCombat(requester);
            return 0;
        }

        tpa.pollLatest(target);
        Messages.actionBar(requester, Messages.tpaAcceptRequester(target.getGameProfile().name()));
        Messages.actionBar(target, Messages.tpaAcceptTarget(requester.getGameProfile().name()));
        tpa.startWarmup(requester, target);
        return 1;
    }

    private int tpdeny(ServerPlayerEntity target) {
        if (denyIfInCombat(target)) {
            return 0;
        }
        TpaManager.Request request = tpa.pollLatest(target);
        if (request == null) {
            Messages.actionBar(target, Messages.tpaNonePending());
            return 0;
        }
        Messages.actionBar(target, Messages.tpaDenyTarget(request.requesterName()));
        ServerPlayerEntity requester = target.getEntityWorld().getServer()
                .getPlayerManager().getPlayer(request.requester());
        if (requester != null) {
            Messages.actionBar(requester, Messages.tpaDenyRequester(target.getGameProfile().name()));
        }
        return 1;
    }

    private int tpablock(ServerPlayerEntity owner, Collection<PlayerConfigEntry> profiles)
            throws CommandSyntaxException {
        if (denyIfInCombat(owner)) {
            return 0;
        }
        int blocked = 0;
        for (PlayerConfigEntry profile : profiles) {
            if (profile.id().equals(owner.getUuid())) {
                Messages.chat(owner, Messages.withPrefix(Messages.blockSelf()));
                continue;
            }
            if (tpa.blocks().block(owner.getUuid(), profile.id(), profile.name())) {
                tpa.dropRequestsFrom(owner.getUuid(), profile.id());
                Messages.chat(owner, Messages.withPrefix(Messages.blockAdded(profile.name())));
                blocked++;
            } else {
                Messages.chat(owner, Messages.withPrefix(Messages.blockAlready(profile.name())));
            }
        }
        return blocked;
    }

    private int tpaunblock(ServerPlayerEntity owner, String targetName) {
        MinecraftServer server = owner.getEntityWorld().getServer();
        UUID blockedId = null;
        String blockedName = targetName;

        ServerPlayerEntity online = server.getPlayerManager().getPlayer(targetName);
        if (online != null) {
            blockedId = online.getUuid();
            blockedName = online.getGameProfile().name();
        } else {
            // Fall back to the name recorded when the block was added, so offline players still work.
            for (Map.Entry<UUID, String> entry : tpa.blocks().blocksOf(owner.getUuid()).entrySet()) {
                if (entry.getValue().equalsIgnoreCase(targetName)) {
                    blockedId = entry.getKey();
                    blockedName = entry.getValue();
                    break;
                }
            }
        }

        if (blockedId == null || !tpa.blocks().unblock(owner.getUuid(), blockedId)) {
            Messages.chat(owner, Messages.withPrefix(Messages.blockNotBlocked(blockedName)));
            return 0;
        }
        Messages.chat(owner, Messages.withPrefix(Messages.blockRemoved(blockedName)));
        return 1;
    }

    private int tpablocks(ServerPlayerEntity owner) {
        Map<UUID, String> blocked = tpa.blocks().blocksOf(owner.getUuid());
        if (blocked.isEmpty()) {
            Messages.chat(owner, Messages.withPrefix(Messages.blockListEmpty()));
            return 0;
        }
        Messages.chat(owner, Messages.withPrefix(
                Messages.blockListHeader(blocked.size(), String.join(", ", blocked.values()))));
        return 1;
    }
}
