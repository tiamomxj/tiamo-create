package dev.mcbuild.harness;

import com.google.gson.Gson;
import com.google.gson.JsonArray;
import com.google.gson.JsonObject;
import net.fabricmc.loader.api.entrypoint.PreLaunchEntrypoint;
import net.minecraft.Bootstrap;
import net.minecraft.SharedConstants;
import net.minecraft.block.Block;
import net.minecraft.block.BlockState;
import net.minecraft.block.SideShapeType;
import net.minecraft.block.entity.BlockEntityType;
import net.minecraft.entity.EntityType;
import net.minecraft.fluid.FluidState;
import net.minecraft.registry.Registries;
import net.minecraft.state.property.Property;
import net.minecraft.util.math.BlockPos;
import net.minecraft.util.math.Box;
import net.minecraft.util.math.Direction;
import net.minecraft.world.EmptyBlockView;

import java.io.OutputStreamWriter;
import java.io.Writer;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.*;
import java.util.zip.GZIPOutputStream;

/**
 * Dumps per-block-state facts computed by the game's own code (no world needed): light emission and opacity,
 * collision boxes, full/center/rigid face support, culling faces, spawnability, fluid, block entity type, item,
 * map colour, hardness and the block class chain. The Python kit uses this for lighting, walkability, support
 * and material checks on any block instead of hand-written lists.
 *
 * Per state: [luminance, opacity, flags, fullFaces, centerFaces, rigidFaces, cullFaces, shapeIndex, mapColor, hardness]
 * Face bit order: down, up, north, south, west, east.
 */
public final class FactsDump implements PreLaunchEntrypoint {
    /** Runs inside Fabric's Knot launcher (dev package-access fixes applied) when -Dmcbuild.facts is set, then exits. */
    @Override
    public void onPreLaunch() {
        String out = System.getProperty("mcbuild.facts");
        if (out == null || out.isBlank()) return;
        try { main(new String[]{out}); } catch (Throwable t) { t.printStackTrace(); System.exit(1); }
        System.exit(0);
    }

    static final Direction[] DIRS = {Direction.DOWN, Direction.UP, Direction.NORTH, Direction.SOUTH, Direction.WEST, Direction.EAST};

    static <T extends Comparable<T>> String value(BlockState s, Property<T> p) { return p.name(s.get(p)); }

    static String props(BlockState s) {
        TreeMap<String, String> m = new TreeMap<>();
        for (Property<?> p : s.getProperties()) m.put(p.getName(), value(s, p));
        StringJoiner j = new StringJoiner(",");
        m.forEach((k, v) -> j.add(k + "=" + v));
        return j.toString();
    }

    static double r(double v) { return Math.round(v * 10000.0) / 10000.0; }

    public static void main(String[] args) throws Exception {
        SharedConstants.createGameVersion();
        Bootstrap.initialize();
        var view = EmptyBlockView.INSTANCE;
        var pos = BlockPos.ORIGIN;
        Map<String, Integer> shapeIdx = new LinkedHashMap<>();
        JsonArray shapes = new JsonArray();
        Map<String, Integer> classIdx = new LinkedHashMap<>();
        JsonArray classes = new JsonArray();
        JsonObject blocks = new JsonObject();
        List<BlockEntityType<?>> beTypes = new ArrayList<>();
        for (BlockEntityType<?> t : Registries.BLOCK_ENTITY_TYPE) beTypes.add(t);
        int count = 0;
        for (Block block : Registries.BLOCK) {
            String id = Registries.BLOCK.getId(block).toString();
            JsonObject b = new JsonObject();
            List<String> chain = new ArrayList<>();
            for (Class<?> c = block.getClass(); c != null && c != Object.class; c = c.getSuperclass()) chain.add(c.getSimpleName());
            String ck = String.join(">", chain);
            Integer ci = classIdx.get(ck);
            if (ci == null) {
                ci = classIdx.size(); classIdx.put(ck, ci);
                JsonArray a = new JsonArray(); chain.forEach(a::add); classes.add(a);
            }
            b.addProperty("class", ci);
            b.addProperty("item", Registries.ITEM.getId(block.asItem()).toString());
            b.addProperty("blast", block.getBlastResistance());
            b.addProperty("default", props(block.getDefaultState()));
            JsonObject states = new JsonObject();
            String be = null;
            for (BlockState s : block.getStateManager().getStates()) {
                int flags = 0;
                if (s.isOpaqueFullCube()) flags |= 1;
                if (s.isSolidBlock(view, pos)) flags |= 2;
                if (s.isFullCube(view, pos)) flags |= 4;
                if (s.isReplaceable()) flags |= 8;
                if (s.allowsSpawning(view, pos, EntityType.ZOMBIE)) flags |= 16;
                if (s.hasBlockEntity()) flags |= 32;
                if (s.isSolid()) flags |= 64;
                if (s.isBurnable()) flags |= 128;
                FluidState fs = s.getFluidState();
                if (!fs.isEmpty()) {
                    String fid = Registries.FLUID.getId(fs.getFluid()).getPath();
                    if (fid.contains("water")) flags |= 256; else if (fid.contains("lava")) flags |= 512;
                    if (fs.isStill()) flags |= 1024;
                }
                if (s.blocksMovement()) flags |= 2048;
                if (s.isTransparent()) flags |= 4096;
                if (s.isAir()) flags |= 8192;
                if (s.exceedsCube()) flags |= 16384;
                if (s.isOpaque()) flags |= 32768;
                if (s.hasSidedTransparency()) flags |= 65536;
                int full = 0, center = 0, rigid = 0, cull = 0;
                for (int i = 0; i < 6; i++) {
                    if (s.isSideSolidFullSquare(view, pos, DIRS[i])) full |= 1 << i;
                    if (s.isSideSolid(view, pos, DIRS[i], SideShapeType.CENTER)) center |= 1 << i;
                    if (s.isSideSolid(view, pos, DIRS[i], SideShapeType.RIGID)) rigid |= 1 << i;
                    if (Block.isFaceFullSquare(s.getCullingFace(DIRS[i]), DIRS[i])) cull |= 1 << i;
                }
                JsonArray boxes = new JsonArray();
                StringBuilder key = new StringBuilder();
                for (Box bx : s.getCollisionShape(view, pos).getBoundingBoxes()) {
                    JsonArray a = new JsonArray();
                    for (double v : new double[]{bx.minX, bx.minY, bx.minZ, bx.maxX, bx.maxY, bx.maxZ}) { a.add(r(v)); key.append(r(v)).append(','); }
                    key.append(';');
                    boxes.add(a);
                }
                Integer si = shapeIdx.get(key.toString());
                if (si == null) { si = shapeIdx.size(); shapeIdx.put(key.toString(), si); shapes.add(boxes); }
                if (s.hasBlockEntity() && be == null) {
                    for (BlockEntityType<?> t : beTypes) if (t.supports(s)) { be = Registries.BLOCK_ENTITY_TYPE.getId(t).toString(); break; }
                }
                JsonArray f = new JsonArray();
                f.add(s.getLuminance()); f.add(s.getOpacity()); f.add(flags); f.add(full); f.add(center); f.add(rigid); f.add(cull);
                f.add(si); f.add(s.getMapColor(view, pos).color); f.add(r(s.getHardness(view, pos)));
                states.add(props(s), f);
                count++;
            }
            if (be != null) b.addProperty("be", be);
            b.add("states", states);
            blocks.add(id, b);
        }
        JsonObject root = new JsonObject();
        root.addProperty("version", SharedConstants.getGameVersion().name());
        root.addProperty("dataVersion", SharedConstants.getGameVersion().dataVersion().id());
        root.addProperty("layout", "luminance,opacity,flags,fullFaces,centerFaces,rigidFaces,cullFaces,shape,mapColor,hardness");
        root.addProperty("flags", "1 opaqueFullCube,2 solidBlock,4 fullCube,8 replaceable,16 zombieCanSpawnOn,32 blockEntity,64 solid,"
                + "128 burnable,256 water,512 lava,1024 fluidSource,2048 blocksMovement,4096 skylightThrough,8192 air,16384 exceedsCube,"
                + "32768 opaque,65536 sidedTransparency");
        root.addProperty("faces", "down,up,north,south,west,east");
        root.add("shapes", shapes);
        root.add("classes", classes);
        root.add("blocks", blocks);
        Path out = Path.of(args.length > 0 ? args[0] : "facts.json.gz").toAbsolutePath();
        Files.createDirectories(out.getParent());
        try (Writer w = new OutputStreamWriter(new GZIPOutputStream(Files.newOutputStream(out)), StandardCharsets.UTF_8)) {
            new Gson().toJson(root, w);
        }
        System.out.println("FACTS_OK " + out + " blocks=" + Registries.BLOCK.size() + " states=" + count + " shapes=" + shapes.size());
    }
}
