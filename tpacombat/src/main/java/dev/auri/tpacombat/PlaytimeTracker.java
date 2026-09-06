package dev.auri.tpacombat;

import net.minecraft.server.MinecraftServer;
import net.minecraft.server.network.ServerPlayerEntity;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.io.Writer;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Instant;
import java.time.ZoneOffset;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;

/**
 * Accumulates connected time per player and writes a report the host can read.
 *
 * <p>Time is banked periodically rather than only on disconnect, so a crash or a hard server kill
 * loses at most one interval instead of an entire session.
 */
public final class PlaytimeTracker {

    private static final Logger LOGGER = LoggerFactory.getLogger("tpacombat");
    private static final DateTimeFormatter STAMP =
            DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss").withZone(ZoneOffset.UTC);

    /** Start of the un-banked slice of each online player's session. */
    private final Map<UUID, Long> sinceLastBank = new ConcurrentHashMap<>();

    private final PlayerDataStore store;
    private int tickCounter;
    private long lastReportAt;

    public PlaytimeTracker(PlayerDataStore store) {
        this.store = store;
    }

    public void onJoin(ServerPlayerEntity player) {
        if (!Config.get().playtime.enabled) {
            return;
        }
        long now = System.currentTimeMillis();
        PlayerProfile profile = store.get(player.getUuid());
        if (profile.firstSeenEpoch == 0L) {
            profile.firstSeenEpoch = now;
        }
        profile.sessions++;
        profile.lastSeenEpoch = now;
        sinceLastBank.put(player.getUuid(), now);
        store.markDirty();
    }

    public void onDisconnect(ServerPlayerEntity player) {
        bank(player.getUuid(), System.currentTimeMillis(), true);
    }

    /** Banks every online player, then rewrites the report if enough time has passed. */
    public void onEndTick(MinecraftServer server) {
        if (!Config.get().playtime.enabled) {
            return;
        }
        if (++tickCounter < 1200) {
            return;
        }
        tickCounter = 0;

        long now = System.currentTimeMillis();
        for (ServerPlayerEntity player : server.getPlayerManager().getPlayerList()) {
            bank(player.getUuid(), now, false);
        }

        long interval = Config.get().playtime.reportIntervalMinutes * 60_000L;
        if (now - lastReportAt >= interval) {
            lastReportAt = now;
            writeReport(server);
        }
    }

    public void onServerStopping(MinecraftServer server) {
        long now = System.currentTimeMillis();
        for (UUID uuid : List.copyOf(sinceLastBank.keySet())) {
            bank(uuid, now, true);
        }
        writeReport(server);
    }

    /**
     * Moves the time since the last bank into the player's total. The marker is reset rather than
     * removed unless they are leaving, so banking mid-session never double-counts.
     */
    private void bank(UUID uuid, long now, boolean leaving) {
        Long start = leaving ? sinceLastBank.remove(uuid) : sinceLastBank.get(uuid);
        if (start == null) {
            return;
        }
        long delta = now - start;
        if (delta > 0) {
            PlayerProfile profile = store.get(uuid);
            profile.playtimeMillis += delta;
            profile.lastSeenEpoch = now;
            store.markDirty();
        }
        if (!leaving) {
            sinceLastBank.put(uuid, now);
        }
    }

    /** Total including the slice not yet banked, so a live query is accurate to the second. */
    public long totalMillis(UUID uuid) {
        long total = store.peek(uuid).playtimeMillis;
        Long start = sinceLastBank.get(uuid);
        return start == null ? total : total + Math.max(0L, System.currentTimeMillis() - start);
    }

    public static String format(long millis) {
        long seconds = millis / 1000L;
        long days = seconds / 86400L;
        long hours = seconds % 86400L / 3600L;
        long minutes = seconds % 3600L / 60L;
        if (days > 0) {
            return days + "d " + hours + "h " + minutes + "m";
        }
        if (hours > 0) {
            return hours + "h " + minutes + "m";
        }
        return minutes + "m";
    }

    private void writeReport(MinecraftServer server) {
        Path path = Path.of(Config.get().playtime.reportFile);
        try {
            Path parent = path.toAbsolutePath().getParent();
            if (parent != null) {
                Files.createDirectories(parent);
            }
            List<Row> rows = rows(server);
            try (Writer writer = Files.newBufferedWriter(path)) {
                if ("csv".equalsIgnoreCase(Config.get().playtime.format)) {
                    writeCsv(writer, rows);
                } else {
                    writeTable(writer, rows);
                }
            }
        } catch (Exception e) {
            LOGGER.error("Failed to write playtime report to {}", path.toAbsolutePath(), e);
        }
    }

    /** One line of the report; also what the op command reads. */
    public record Row(UUID uuid, String name, long millis, int sessions,
                      long firstSeen, long lastSeen, boolean online) {
    }

    /** Tracked players, longest played first. */
    public List<Row> rows(MinecraftServer server) {
        List<Row> rows = new ArrayList<>();
        for (Map.Entry<UUID, PlayerProfile> entry : store.all().entrySet()) {
            PlayerProfile profile = entry.getValue();
            if (profile.playtimeMillis <= 0L && profile.sessions == 0) {
                continue;
            }
            UUID uuid = entry.getKey();
            String name = profile.lastKnownName == null || profile.lastKnownName.isEmpty()
                    ? uuid.toString().substring(0, 8)
                    : profile.lastKnownName;
            rows.add(new Row(uuid, name, totalMillis(uuid), profile.sessions,
                    profile.firstSeenEpoch, profile.lastSeenEpoch,
                    server.getPlayerManager().getPlayer(uuid) != null));
        }
        rows.sort((a, b) -> Long.compare(b.millis(), a.millis()));
        return rows;
    }

    /** Aligned fixed-width report, meant to be read in a text editor. */
    private static void writeTable(Writer writer, List<Row> rows) throws Exception {
        int rankWidth = Math.max(1, String.valueOf(rows.size()).length());
        int nameWidth = "PLAYER".length();
        int timeWidth = "PLAYTIME".length();
        for (Row row : rows) {
            nameWidth = Math.max(nameWidth, row.name().length());
            timeWidth = Math.max(timeWidth, format(row.millis()).length());
        }

        long totalMillis = 0L;
        int online = 0;
        for (Row row : rows) {
            totalMillis += row.millis();
            if (row.online()) {
                online++;
            }
        }

        String title = Config.get().tablist.serverName + " - Playtime";
        writer.write(title + "\n");
        writer.write("Updated " + stamp(System.currentTimeMillis()) + " UTC\n");
        writer.write(rows.size() + " players tracked, " + online + " online, "
                + format(totalMillis) + " total\n\n");

        String header = "  " + pad("#", rankWidth, true) + "  " + pad("PLAYER", nameWidth, false)
                + "  " + pad("PLAYTIME", timeWidth, true) + "  SESSIONS  LAST SEEN (UTC)";
        writer.write(header + "\n");
        writer.write("  " + "-".repeat(Math.max(header.length() - 2, 10)) + "\n");

        int rank = 0;
        for (Row row : rows) {
            rank++;
            writer.write("  " + pad(String.valueOf(rank), rankWidth, true)
                    + "  " + pad(row.name(), nameWidth, false)
                    + "  " + pad(format(row.millis()), timeWidth, true)
                    + "  " + pad(String.valueOf(row.sessions()), 8, true)
                    + "  " + (row.online() ? "online now" : shortStamp(row.lastSeen()))
                    + "\n");
        }
        if (rows.isEmpty()) {
            writer.write("  (nobody has joined yet)\n");
        }
    }

    private static String pad(String value, int width, boolean right) {
        if (value.length() >= width) {
            return value;
        }
        String spaces = " ".repeat(width - value.length());
        return right ? spaces + value : value + spaces;
    }

    private static void writeCsv(Writer writer, List<Row> rows) throws Exception {
        writer.write("uuid,name,playtime_seconds,playtime,sessions,first_seen_utc,last_seen_utc,online\n");
        for (Row row : rows) {
            writer.write(String.join(",",
                    row.uuid().toString(),
                    csv(row.name()),
                    String.valueOf(row.millis() / 1000L),
                    csv(format(row.millis())),
                    String.valueOf(row.sessions()),
                    csv(stamp(row.firstSeen())),
                    csv(stamp(row.lastSeen())),
                    String.valueOf(row.online())));
            writer.write("\n");
        }
    }

    private static String stamp(long epochMillis) {
        return epochMillis == 0L ? "" : STAMP.format(Instant.ofEpochMilli(epochMillis));
    }

    /** Minute-precision timestamp, or a dash when the player has never been seen. */
    public static String stampOrDash(long epochMillis) {
        return shortStamp(epochMillis);
    }

    /** Minute precision is plenty for a "last seen" column and keeps it narrow. */
    private static String shortStamp(long epochMillis) {
        String full = stamp(epochMillis);
        return full.isEmpty() ? "-" : full.substring(0, 16);
    }

    /** Names are Mojang-constrained, but quote defensively so the CSV cannot be broken. */
    private static String csv(String value) {
        if (value == null) {
            return "";
        }
        if (value.contains(",") || value.contains("\"") || value.contains("\n")) {
            return "\"" + value.replace("\"", "\"\"") + "\"";
        }
        return value;
    }
}
