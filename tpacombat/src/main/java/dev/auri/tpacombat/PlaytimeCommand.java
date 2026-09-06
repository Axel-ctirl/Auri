package dev.auri.tpacombat;

import com.mojang.brigadier.CommandDispatcher;
import com.mojang.brigadier.arguments.IntegerArgumentType;
import com.mojang.brigadier.arguments.StringArgumentType;
import net.minecraft.command.CommandSource;
import net.minecraft.server.MinecraftServer;
import net.minecraft.server.command.CommandManager;
import net.minecraft.server.command.ServerCommandSource;
import net.minecraft.text.MutableText;
import net.minecraft.text.Text;
import net.minecraft.util.Formatting;

import java.util.List;

/**
 * Operator view of the tracked playtime, so the report can be checked without opening a file.
 * Gated at permission level 2, which ops meet and ordinary players do not.
 */
public final class PlaytimeCommand {

    private static final int DEFAULT_LIMIT = 10;

    private final PlaytimeTracker tracker;

    public PlaytimeCommand(PlaytimeTracker tracker) {
        this.tracker = tracker;
    }

    public void register(CommandDispatcher<ServerCommandSource> dispatcher) {
        dispatcher.register(CommandManager.literal("playtime")
                // 1.21.11 replaced hasPermissionLevel with permission checks; GAMEMASTERS is the
                // level vanilla uses for operator tooling, which any op satisfies.
                .requires(CommandManager.requirePermissionLevel(CommandManager.GAMEMASTERS_CHECK))
                .executes(context -> top(context.getSource(), DEFAULT_LIMIT))
                .then(CommandManager.literal("top")
                        .executes(context -> top(context.getSource(), DEFAULT_LIMIT))
                        .then(CommandManager.argument("count", IntegerArgumentType.integer(1, 100))
                                .executes(context -> top(context.getSource(),
                                        IntegerArgumentType.getInteger(context, "count")))))
                .then(CommandManager.argument("player", StringArgumentType.word())
                        .suggests((context, builder) -> CommandSource.suggestMatching(
                                names(context.getSource().getServer()), builder))
                        .executes(context -> lookup(context.getSource(),
                                StringArgumentType.getString(context, "player")))));
    }

    private List<String> names(MinecraftServer server) {
        return tracker.rows(server).stream().map(PlaytimeTracker.Row::name).toList();
    }

    private int top(ServerCommandSource source, int limit) {
        List<PlaytimeTracker.Row> rows = tracker.rows(source.getServer());
        if (rows.isEmpty()) {
            source.sendFeedback(() -> Messages.withPrefix(
                    Text.literal("Nobody has any tracked playtime yet.").formatted(Formatting.YELLOW)), false);
            return 0;
        }

        int shown = Math.min(limit, rows.size());
        source.sendFeedback(() -> Messages.withPrefix(Text.empty()
                .append(Text.literal("Top " + shown).formatted(Formatting.YELLOW))
                .append(Text.literal(" of ").formatted(Formatting.GRAY))
                .append(Text.literal(rows.size() + " tracked").formatted(Formatting.WHITE))), false);

        for (int i = 0; i < shown; i++) {
            PlaytimeTracker.Row row = rows.get(i);
            int rank = i + 1;
            MutableText line = Text.empty()
                    .append(Text.literal(rank + ". ").formatted(Formatting.DARK_GRAY))
                    .append(Text.literal(row.name()).formatted(row.online() ? Formatting.GREEN : Formatting.WHITE))
                    .append(Text.literal(" - ").formatted(Formatting.DARK_GRAY))
                    .append(Text.literal(PlaytimeTracker.format(row.millis())).formatted(Formatting.AQUA));
            if (row.online()) {
                line.append(Text.literal(" (online)").formatted(Formatting.GRAY));
            }
            source.sendFeedback(() -> line, false);
        }
        return shown;
    }

    private int lookup(ServerCommandSource source, String name) {
        List<PlaytimeTracker.Row> rows = tracker.rows(source.getServer());
        PlaytimeTracker.Row match = rows.stream()
                .filter(row -> row.name().equalsIgnoreCase(name))
                .findFirst()
                .orElse(null);
        if (match == null) {
            source.sendFeedback(() -> Messages.withPrefix(Text.empty()
                    .append(Text.literal(name).formatted(Formatting.WHITE))
                    .append(Text.literal(" has no tracked playtime.").formatted(Formatting.RED))), false);
            return 0;
        }

        source.sendFeedback(() -> Messages.withPrefix(Text.empty()
                .append(Text.literal(match.name()).formatted(Formatting.WHITE))
                .append(Text.literal(" - ").formatted(Formatting.DARK_GRAY))
                .append(Text.literal(PlaytimeTracker.format(match.millis())).formatted(Formatting.AQUA))
                .append(Text.literal(" over ").formatted(Formatting.GRAY))
                .append(Text.literal(match.sessions() + (match.sessions() == 1 ? " session" : " sessions"))
                        .formatted(Formatting.WHITE))), false);
        source.sendFeedback(() -> Messages.withPrefix(Text.empty()
                .append(Text.literal("First seen ").formatted(Formatting.GRAY))
                .append(Text.literal(PlaytimeTracker.stampOrDash(match.firstSeen())).formatted(Formatting.WHITE))
                .append(Text.literal(", last seen ").formatted(Formatting.GRAY))
                .append(Text.literal(match.online() ? "online now"
                        : PlaytimeTracker.stampOrDash(match.lastSeen())).formatted(Formatting.WHITE))), false);
        return 1;
    }
}
