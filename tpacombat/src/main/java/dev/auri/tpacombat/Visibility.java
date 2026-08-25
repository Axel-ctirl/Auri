package dev.auri.tpacombat;

import net.minecraft.util.Formatting;

/** Who is allowed to reach you, used for TPA requests and private messages. */
public enum Visibility {

    EVERYONE("Everyone", Formatting.GREEN),
    FRIENDS("Friends", Formatting.YELLOW),
    FOLLOWING("Following", Formatting.GOLD),
    NOBODY("Nobody", Formatting.RED);

    private final String label;
    private final Formatting color;

    Visibility(String label, Formatting color) {
        this.label = label;
        this.color = color;
    }

    public String label() {
        return label;
    }

    public Formatting color() {
        return color;
    }

    public Visibility next() {
        Visibility[] all = values();
        return all[(ordinal() + 1) % all.length];
    }

    /** "Following" means people the owner follows; "Friends" means the follow is mutual. */
    public boolean allows(SocialManager social, java.util.UUID owner, java.util.UUID sender) {
        return switch (this) {
            case EVERYONE -> true;
            case FRIENDS -> social.areFriends(owner, sender);
            case FOLLOWING -> social.isFollowing(owner, sender);
            case NOBODY -> false;
        };
    }

    public String deniedReason() {
        return switch (this) {
            case EVERYONE -> "";
            case FRIENDS -> "only accepts requests from friends";
            case FOLLOWING -> "only accepts requests from people they follow";
            case NOBODY -> "is not accepting requests";
        };
    }
}
