package dev.auri.tpacombat;

import com.mojang.brigadier.CommandDispatcher;
import net.minecraft.command.CommandSource;
import net.minecraft.server.command.CommandManager;
import net.minecraft.server.command.ServerCommandSource;
import net.minecraft.server.network.ServerPlayerEntity;
import net.minecraft.text.Text;
import net.minecraft.util.Formatting;

import com.mojang.brigadier.arguments.StringArgumentType;

public final class SettingsCommands {

    private final PlayerDataStore store;

    public SettingsCommands(PlayerDataStore store) {
        this.store = store;
    }

    public void register(CommandDispatcher<ServerCommandSource> dispatcher) {
        var root = CommandManager.literal("settings")
                .executes(context -> {
                    ServerPlayerEntity player = context.getSource().getPlayerOrThrow();
                    SettingsDialogs.openRoot(player, store.get(player.getUuid()));
                    return 1;
                });

        for (SettingsRegistry.Category category : SettingsRegistry.categories()) {
            root = root.then(CommandManager.literal(category.id()).executes(context -> {
                ServerPlayerEntity player = context.getSource().getPlayerOrThrow();
                SettingsDialogs.openCategory(player, store.get(player.getUuid()), category.id());
                return 1;
            }));
        }

        root = root.then(CommandManager.literal("friendsfilter").executes(context -> {
            ServerPlayerEntity player = context.getSource().getPlayerOrThrow();
            PlayerProfile profile = store.get(player.getUuid());
            profile.friendsFilter = switch (profile.friendsFilter) {
                case "friends" -> "following";
                case "following" -> "followers";
                default -> "friends";
            };
            store.markDirty();
            SettingsDialogs.openFriends(player, profile);
            return 1;
        }));

        root = root.then(CommandManager.literal("friendsearch").executes(context -> {
            SettingsDialogs.openSearch(context.getSource().getPlayerOrThrow());
            return 1;
        }));

        root = root.then(CommandManager.literal("finduser")
                .then(CommandManager.argument("name", StringArgumentType.word())
                        .executes(context -> findUser(context.getSource().getPlayerOrThrow(),
                                StringArgumentType.getString(context, "name")))));

        root = root.then(CommandManager.literal("unfollowid")
                .then(CommandManager.argument("uuid", StringArgumentType.word())
                        .executes(context -> unfollowId(context.getSource().getPlayerOrThrow(),
                                StringArgumentType.getString(context, "uuid")))));

        root = root.then(CommandManager.literal("cycle")
                .then(CommandManager.argument("setting", StringArgumentType.word())
                        .suggests((context, builder) -> CommandSource.suggestMatching(SettingsRegistry.ids(), builder))
                        .executes(context -> cycle(context.getSource().getPlayerOrThrow(),
                                StringArgumentType.getString(context, "setting")))));

        dispatcher.register(root);
    }

    /** Unfollow addressed by UUID, so friend-list buttons work for offline players. */
    private int unfollowId(ServerPlayerEntity player, String uuid) {
        PlayerProfile profile = store.get(player.getUuid());
        try {
            java.util.UUID target = java.util.UUID.fromString(uuid);
            SocialManager social = TpaCombat.social();
            String name = social.nameOf(player.getEntityWorld().getServer(), target);
            if (social.unfollow(player.getUuid(), target)) {
                player.sendMessage(Messages.withPrefix(
                        Text.literal("You no longer follow ").formatted(Formatting.YELLOW)
                                .append(Text.literal(name).formatted(Formatting.WHITE))
                                .append(Text.literal(".").formatted(Formatting.YELLOW))));
            }
        } catch (IllegalArgumentException ignored) {
            // malformed uuid: fall through and just re-open the list
        }
        SettingsDialogs.openFriends(player, profile);
        return 1;
    }

    /** Search result: follow the named player if they are online, then return to the list. */
    private int findUser(ServerPlayerEntity player, String name) {
        ServerPlayerEntity target = player.getEntityWorld().getServer().getPlayerManager().getPlayer(name);
        PlayerProfile profile = store.get(player.getUuid());
        if (target == null) {
            player.sendMessage(Messages.withPrefix(Messages.playerNotFound(name)));
        } else if (target.getUuid().equals(player.getUuid())) {
            player.sendMessage(Messages.withPrefix(
                    Text.literal("You can't follow yourself.").formatted(Formatting.RED)));
        } else {
            player.getEntityWorld().getServer().getCommandManager().parseAndExecute(
                    player.getCommandSource(), "follow " + target.getGameProfile().name());
        }
        SettingsDialogs.openFriends(player, profile);
        return 1;
    }

    private int cycle(ServerPlayerEntity player, String id) {
        SettingDef setting = SettingsRegistry.byId(id);
        if (setting == null) {
            player.sendMessage(Messages.withPrefix(
                    Text.literal("Unknown setting: " + id).formatted(Formatting.RED)));
            return 0;
        }
        PlayerProfile profile = store.get(player.getUuid());
        setting.cycle(profile);
        store.markDirty();
        // Re-open the same category so the client's waiting screen resolves into the updated menu.
        SettingsDialogs.openCategory(player, profile, setting.category());
        return 1;
    }
}
