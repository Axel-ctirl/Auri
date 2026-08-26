package dev.auri.tpacombat;

import java.util.LinkedHashSet;
import java.util.Set;

/** Per-player settings plus the people they follow. Serialised straight to JSON by GSON. */
public final class PlayerProfile {

    // Chat
    public boolean publicChat = true;
    public Visibility privateMessages = Visibility.EVERYONE;
    public boolean serverMessages = true;
    public boolean deathMessages = true;
    public boolean advancementMessages = true;
    public boolean joinLeaveMessages = true;

    // Notifications
    public boolean tpaAlerts = true;
    public boolean combatAlerts = true;

    // PvP (purely client-side visuals; the underlying effects still apply)
    public boolean totemParticles = true;
    public boolean explosionParticles = true;

    // Privacy
    public Visibility tpaRequests = Visibility.EVERYONE;

    // General
    /** When false, phantoms stop spawning around this player. */
    public boolean phantomSpawning = true;
    /** When false, this player's in-flight ender pearls are discarded when they die. */
    public boolean keepEnderPearlsOnDeath = true;
    public boolean nightVision = false;

    // Social — UUID strings so GSON round-trips them without a custom adapter.
    public Set<String> following = new LinkedHashSet<>();

    /** Which list the Friends tab is showing: friends, following or followers. */
    public String friendsFilter = "friends";

    /** Last name seen for this player, so offline lookups can show something useful. */
    public String lastKnownName = "";

    /** GSON leaves fields absent from the file as null, so repair them after loading. */
    public void repair() {
        if (privateMessages == null) {
            privateMessages = Visibility.EVERYONE;
        }
        if (tpaRequests == null) {
            tpaRequests = Visibility.EVERYONE;
        }
        if (following == null) {
            following = new LinkedHashSet<>();
        }
        if (lastKnownName == null) {
            lastKnownName = "";
        }
        if (friendsFilter == null) {
            friendsFilter = "friends";
        }
    }
}
