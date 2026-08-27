package dev.auri.tpacombat;

import com.google.gson.Gson;
import com.google.gson.GsonBuilder;
import com.google.gson.reflect.TypeToken;
import net.minecraft.server.MinecraftServer;
import net.minecraft.util.WorldSavePath;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.io.Reader;
import java.io.Writer;
import java.lang.reflect.Type;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;

/** Profiles keyed by UUID, stored beside the world save so they travel with it. */
public final class PlayerDataStore {

    private static final Logger LOGGER = LoggerFactory.getLogger("tpacombat");
    private static final Gson GSON = new GsonBuilder().setPrettyPrinting().create();
    private static final Type TYPE = new TypeToken<Map<String, PlayerProfile>>() {
    }.getType();
    private static final String FILE_NAME = "tpacombat_players.json";

    private final Map<UUID, PlayerProfile> profiles = new ConcurrentHashMap<>();
    private volatile Path path;
    private volatile boolean dirty;

    public void load(MinecraftServer server) {
        profiles.clear();
        path = server.getSavePath(WorldSavePath.ROOT).resolve("data").resolve(FILE_NAME);
        if (!Files.exists(path)) {
            return;
        }
        try (Reader reader = Files.newBufferedReader(path)) {
            Map<String, PlayerProfile> raw = GSON.fromJson(reader, TYPE);
            if (raw == null) {
                return;
            }
            raw.forEach((key, profile) -> {
                if (profile == null) {
                    return;
                }
                try {
                    profile.repair();
                    profiles.put(UUID.fromString(key), profile);
                } catch (IllegalArgumentException ignored) {
                    // skip an unparseable uuid rather than failing the whole load
                }
            });
        } catch (Exception e) {
            LOGGER.error("Failed to read {}, starting with default profiles", path, e);
        }
        dirty = false;
    }

    public void save() {
        Path target = path;
        if (target == null) {
            return;
        }
        try {
            Files.createDirectories(target.getParent());
            Map<String, PlayerProfile> raw = new LinkedHashMap<>();
            profiles.forEach((uuid, profile) -> raw.put(uuid.toString(), profile));
            try (Writer writer = Files.newBufferedWriter(target)) {
                GSON.toJson(raw, TYPE, writer);
            }
            dirty = false;
        } catch (Exception e) {
            LOGGER.error("Failed to write {}", target, e);
        }
    }

    /** Writes at most once a minute, so a burst of toggles costs one file write. */
    public void saveIfDirty() {
        if (dirty) {
            save();
        }
    }

    public void markDirty() {
        dirty = true;
    }

    private static final PlayerProfile DEFAULTS = new PlayerProfile();

    /** Creates and stores a profile. Use only when the caller is about to change something. */
    public PlayerProfile get(UUID uuid) {
        return profiles.computeIfAbsent(uuid, k -> new PlayerProfile());
    }

    /**
     * Read-only lookup that never inserts. Hot paths use this so that merely reading a setting
     * cannot grow the map, and so packet filtering stays a plain read.
     */
    public PlayerProfile peek(UUID uuid) {
        PlayerProfile profile = profiles.get(uuid);
        return profile == null ? DEFAULTS : profile;
    }

    public Map<UUID, PlayerProfile> all() {
        return profiles;
    }
}
