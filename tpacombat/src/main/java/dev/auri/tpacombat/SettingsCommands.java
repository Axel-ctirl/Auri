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

        root = root.then(CommandManager.literal("cycle")
                .then(CommandManager.argument("setting", StringArgumentType.word())
                        .suggests((context, builder) -> CommandSource.suggestMatching(SettingsRegistry.ids(), builder))
                        .executes(context -> cycle(context.getSource().getPlayerOrThrow(),
                                StringArgumentType.getString(context, "setting")))));

        dispatcher.register(root);
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
