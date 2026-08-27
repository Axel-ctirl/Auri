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
    private final PlayerEffects effects;

    public SettingsCommands(PlayerDataStore store, PlayerEffects effects) {
        this.store = store;
        this.effects = effects;
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

        root = root.then(CommandManager.literal("open")
                .then(CommandManager.argument("setting", StringArgumentType.word())
                        .suggests((context, builder) -> CommandSource.suggestMatching(SettingsRegistry.ids(), builder))
                        .executes(context -> openSetting(context.getSource().getPlayerOrThrow(),
                                StringArgumentType.getString(context, "setting")))));

        root = root.then(CommandManager.literal("set")
                .then(CommandManager.argument("setting", StringArgumentType.word())
                        .suggests((context, builder) -> CommandSource.suggestMatching(SettingsRegistry.ids(), builder))
                        .then(CommandManager.argument("value", StringArgumentType.word())
                                .suggests(SettingsCommands::suggestValues)
                                .executes(context -> setValue(context.getSource().getPlayerOrThrow(),
                                        StringArgumentType.getString(context, "setting"),
                                        StringArgumentType.getString(context, "value"))))));

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

    private static java.util.concurrent.CompletableFuture<com.mojang.brigadier.suggestion.Suggestions>
            suggestValues(com.mojang.brigadier.context.CommandContext<ServerCommandSource> context,
                          com.mojang.brigadier.suggestion.SuggestionsBuilder builder) {
        SettingDef setting = SettingsRegistry.byId(StringArgumentType.getString(context, "setting"));
        return setting == null
                ? builder.buildFuture()
                : CommandSource.suggestMatching(setting.optionKeys(), builder);
    }

    private int openSetting(ServerPlayerEntity player, String id) {
        SettingDef setting = SettingsRegistry.byId(id);
        if (setting == null) {
            return unknown(player, id);
        }
        SettingsDialogs.openSetting(player, store.get(player.getUuid()), setting);
        return 1;
    }

    private int setValue(ServerPlayerEntity player, String id, String value) {
        SettingDef setting = SettingsRegistry.byId(id);
        if (setting == null) {
            return unknown(player, id);
        }
        PlayerProfile profile = store.get(player.getUuid());
        if (!setting.apply(profile, value)) {
            player.sendMessage(Messages.withPrefix(Text.literal(
                    "\"" + value + "\" is not a value for " + setting.label() + ".")
                    .formatted(Formatting.RED)));
            SettingsDialogs.openSetting(player, profile, setting);
            return 0;
        }
        store.markDirty();
        // Night vision and phantom suppression otherwise wait for the next sweep, which reads as lag.
        effects.applyNow(player);
        // Back to the category, so choosing a value returns you to where you came from.
        SettingsDialogs.openCategory(player, profile, setting.category());
        return 1;
    }

    private int unknown(ServerPlayerEntity player, String id) {
        player.sendMessage(Messages.withPrefix(
                Text.literal("Unknown setting: " + id).formatted(Formatting.RED)));
        return 0;
    }
}
