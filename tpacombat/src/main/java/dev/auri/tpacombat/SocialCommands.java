package dev.auri.tpacombat;

import com.mojang.brigadier.CommandDispatcher;
import net.minecraft.command.argument.EntityArgumentType;
import net.minecraft.server.MinecraftServer;
import net.minecraft.server.command.CommandManager;
import net.minecraft.server.command.ServerCommandSource;
import net.minecraft.server.network.ServerPlayerEntity;
import net.minecraft.text.MutableText;
import net.minecraft.text.Text;
import net.minecraft.util.Formatting;

import java.util.List;
import java.util.UUID;
import java.util.function.Function;

public final class SocialCommands {

    private final SocialManager social;
    private final PlayerDataStore store;

    public SocialCommands(SocialManager social, PlayerDataStore store) {
        this.social = social;
        this.store = store;
    }

    public void register(CommandDispatcher<ServerCommandSource> dispatcher) {
        dispatcher.register(CommandManager.literal("follow")
                .then(CommandManager.argument("player", EntityArgumentType.player())
                        .executes(context -> follow(context.getSource().getPlayerOrThrow(),
                                EntityArgumentType.getPlayer(context, "player")))));

        dispatcher.register(CommandManager.literal("unfollow")
                .then(CommandManager.argument("player", EntityArgumentType.player())
                        .executes(context -> unfollow(context.getSource().getPlayerOrThrow(),
                                EntityArgumentType.getPlayer(context, "player")))));

        dispatcher.register(CommandManager.literal("following")
                .executes(context -> list(context.getSource().getPlayerOrThrow(), "Following", social::following)));

        dispatcher.register(CommandManager.literal("followers")
                .executes(context -> list(context.getSource().getPlayerOrThrow(), "Followers", social::followers)));

        dispatcher.register(CommandManager.literal("friends")
                .executes(context -> list(context.getSource().getPlayerOrThrow(), "Friends", social::friends)));
    }

    private int follow(ServerPlayerEntity owner, ServerPlayerEntity target) {
        if (owner.getUuid().equals(target.getUuid())) {
            owner.sendMessage(Messages.withPrefix(
                    Text.literal("You can't follow yourself.").formatted(Formatting.RED)));
            return 0;
        }
        String targetName = target.getGameProfile().name();
        if (!social.follow(owner.getUuid(), target.getUuid(), targetName)) {
            owner.sendMessage(Messages.withPrefix(name(targetName)
                    .append(Text.literal(" is already followed.").formatted(Formatting.RED))));
            return 0;
        }
        store.get(owner.getUuid()).lastKnownName = owner.getGameProfile().name();

        boolean mutual = social.areFriends(owner.getUuid(), target.getUuid());
        owner.sendMessage(Messages.withPrefix(Text.literal("You now follow ").formatted(Formatting.GREEN)
                .append(name(targetName))
                .append(Text.literal(mutual ? " - you are now friends!" : ".").formatted(Formatting.GREEN))));

        // Tell the other player, since a follow-back is what turns this into a friendship.
        target.sendMessage(Messages.withPrefix(name(owner.getGameProfile().name())
                .append(Text.literal(mutual
                        ? " followed you back - you are now friends!"
                        : " started following you.").formatted(Formatting.GOLD))));
        return 1;
    }

    private int unfollow(ServerPlayerEntity owner, ServerPlayerEntity target) {
        String targetName = target.getGameProfile().name();
        if (!social.unfollow(owner.getUuid(), target.getUuid())) {
            owner.sendMessage(Messages.withPrefix(name(targetName)
                    .append(Text.literal(" is not on your following list.").formatted(Formatting.RED))));
            return 0;
        }
        owner.sendMessage(Messages.withPrefix(Text.literal("You no longer follow ").formatted(Formatting.YELLOW)
                .append(name(targetName)).append(Text.literal(".").formatted(Formatting.YELLOW))));
        return 1;
    }

    private int list(ServerPlayerEntity owner, String heading, Function<UUID, List<UUID>> lookup) {
        MinecraftServer server = owner.getEntityWorld().getServer();
        List<UUID> ids = lookup.apply(owner.getUuid());
        if (ids.isEmpty()) {
            owner.sendMessage(Messages.withPrefix(
                    Text.literal(heading + ": none yet.").formatted(Formatting.YELLOW)));
            return 0;
        }
        StringBuilder names = new StringBuilder();
        for (UUID id : ids) {
            if (names.length() > 0) {
                names.append(", ");
            }
            names.append(social.nameOf(server, id));
        }
        owner.sendMessage(Messages.withPrefix(Text.empty()
                .append(Text.literal(heading + " (").formatted(Formatting.YELLOW))
                .append(Text.literal(String.valueOf(ids.size())).formatted(Formatting.WHITE))
                .append(Text.literal("): ").formatted(Formatting.YELLOW))
                .append(Text.literal(names.toString()).formatted(Formatting.WHITE))));
        return 1;
    }

    private static MutableText name(String value) {
        return Text.literal(value).formatted(Formatting.WHITE);
    }
}
