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

            List<Map.Entry<UUID, PlayerProfile>> rows = new ArrayList<>(store.all().entrySet());
            rows.removeIf(e -> e.getValue().playtimeMillis <= 0L && e.getValue().sessions == 0);
            rows.sort((a, b) -> Long.compare(totalMillis(b.getKey()), totalMillis(a.getKey())));

            try (Writer writer = Files.newBufferedWriter(path)) {
                writer.write("uuid,name,playtime_seconds,playtime,sessions,first_seen_utc,last_seen_utc,online\n");
                for (Map.Entry<UUID, PlayerProfile> row : rows) {
                    UUID uuid = row.getKey();
                    PlayerProfile profile = row.getValue();
                    long millis = totalMillis(uuid);
                    boolean online = server.getPlayerManager().getPlayer(uuid) != null;
                    writer.write(String.join(",",
                            uuid.toString(),
                            csv(profile.lastKnownName),
                            String.valueOf(millis / 1000L),
                            csv(format(millis)),
                            String.valueOf(profile.sessions),
                            csv(stamp(profile.firstSeenEpoch)),
                            csv(stamp(profile.lastSeenEpoch)),
                            String.valueOf(online)));
                    writer.write("\n");
                }
            }
        } catch (Exception e) {
            LOGGER.error("Failed to write playtime report to {}", path.toAbsolutePath(), e);
        }
    }

    private static String stamp(long epochMillis) {
        return epochMillis == 0L ? "" : STAMP.format(Instant.ofEpochMilli(epochMillis));
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
