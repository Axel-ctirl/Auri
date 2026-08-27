package dev.auri.tpacombat;

import com.mojang.authlib.GameProfile;
import net.minecraft.component.type.ProfileComponent;
import net.minecraft.text.MutableText;
import net.minecraft.text.ObjectTextContent;
import net.minecraft.text.object.AtlasTextObjectContents;
import net.minecraft.text.object.PlayerTextObjectContents;
import net.minecraft.util.Atlases;
import net.minecraft.util.Identifier;

/**
 * Inline icons for menu labels, using the "object" text component added in 1.21.9. Vanilla clients
 * render these natively, so buttons can carry real item textures and player heads instead of
 * unicode stand-ins.
 */
public final class Icons {

    private Icons() {
    }

    /**
     * {@code sprite} is a texture path such as {@code item/diamond_sword}.
     *
     * <p>Item textures live in the {@code minecraft:items} atlas, not the {@code minecraft:blocks}
     * atlas that {@link AtlasTextObjectContents#DEFAULT_ATLAS} points at -- blocks.json only
     * sources the {@code block/} directory, so an item sprite looked up there resolves to nothing
     * and renders blank.
     */
    public static MutableText item(String sprite) {
        return MutableText.of(new ObjectTextContent(new AtlasTextObjectContents(
                Atlases.ITEMS, Identifier.ofVanilla(sprite))));
    }

    /** Block textures, which do live in the default {@code minecraft:blocks} atlas. */
    public static MutableText block(String sprite) {
        return MutableText.of(new ObjectTextContent(new AtlasTextObjectContents(
                Atlases.BLOCKS, Identifier.ofVanilla(sprite))));
    }

    /** Player heads are fixed at 8x8 in vanilla, which lines up with a text line. */
    public static MutableText head(GameProfile profile) {
        return MutableText.of(new ObjectTextContent(
                new PlayerTextObjectContents(ProfileComponent.ofStatic(profile), true)));
    }
}
