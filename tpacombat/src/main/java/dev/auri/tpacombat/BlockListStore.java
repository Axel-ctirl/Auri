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
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.UUID;

/**
 * Per-player TPA block lists. The original stored these in a Forge {@code SavedData} attached to
 * the overworld; this keeps the same "travels with the world save" behaviour by writing
 * {@code <world>/data/tpacombat_blocks.json}.
 *
 * <p>Outer key is the owner (the player doing the blocking), inner map is blocked UUID to the
 * name last seen for them, so /tpaunblock can work on offline players by name.
 */
public final class BlockListStore {

    private static final Logger LOGGER = LoggerFactory.getLogger("tpacombat");
    private static final Gson GSON = new GsonBuilder().setPrettyPrinting().create();
    private static final Type TYPE = new TypeToken<Map<String, Map<String, String>>>() {
    }.getType();
    private static final String FILE_NAME = "tpacombat_blocks.json";

    private final Map<UUID, Map<UUID, String>> blocks = new LinkedHashMap<>();
    private Path path;

    public void load(MinecraftServer server) {
        blocks.clear();
        path = server.getSavePath(WorldSavePath.ROOT).resolve("data").resolve(FILE_NAME);
        if (!Files.exists(path)) {
            return;
        }
        try (Reader reader = Files.newBufferedReader(path)) {
            Map<String, Map<String, String>> raw = GSON.fromJson(reader, TYPE);
            if (raw == null) {
                return;
            }
            raw.forEach((ownerKey, owned) -> {
                if (owned == null || owned.isEmpty()) {
                    return;
                }
                try {
                    UUID owner = UUID.fromString(ownerKey);
                    Map<UUID, String> parsed = new LinkedHashMap<>();
                    owned.forEach((blockedKey, name) -> {
                        try {
                            parsed.put(UUID.fromString(blockedKey), name);
                        } catch (IllegalArgumentException ignored) {
                            // drop unparseable entries rather than failing the whole load
                        }
                    });
                    if (!parsed.isEmpty()) {
                        blocks.put(owner, parsed);
                    }
                } catch (IllegalArgumentException ignored) {
                    // same for a bad owner key
                }
            });
        } catch (Exception e) {
            LOGGER.error("Failed to read {}, starting with empty block lists", path, e);
        }
    }

    public void save() {
        if (path == null) {
            return;
        }
        try {
            Files.createDirectories(path.getParent());
            Map<String, Map<String, String>> raw = new LinkedHashMap<>();
            blocks.forEach((owner, owned) -> {
                Map<String, String> out = new LinkedHashMap<>();
                owned.forEach((blocked, name) -> out.put(blocked.toString(), name));
                raw.put(owner.toString(), out);
            });
            try (Writer writer = Files.newBufferedWriter(path)) {
                GSON.toJson(raw, TYPE, writer);
            }
        } catch (Exception e) {
            LOGGER.error("Failed to write {}", path, e);
        }
    }

    public boolean isBlocked(UUID owner, UUID requester) {
        Map<UUID, String> owned = blocks.get(owner);
        return owned != null && owned.containsKey(requester);
    }

    public boolean block(UUID owner, UUID blocked, String blockedName) {
        Map<UUID, String> owned = blocks.computeIfAbsent(owner, k -> new LinkedHashMap<>());
        boolean added = owned.put(blocked, blockedName) == null;
        if (added) {
            save();
        }
        return added;
    }

    public boolean unblock(UUID owner, UUID blocked) {
        Map<UUID, String> owned = blocks.get(owner);
        if (owned == null || owned.remove(blocked) == null) {
            return false;
        }
        if (owned.isEmpty()) {
            blocks.remove(owner);
        }
        save();
        return true;
    }

    public Map<UUID, String> blocksOf(UUID owner) {
        Map<UUID, String> owned = blocks.get(owner);
        return owned == null ? Collections.emptyMap() : Collections.unmodifiableMap(owned);
    }
}
