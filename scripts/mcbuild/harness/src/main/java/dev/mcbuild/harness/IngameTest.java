package dev.mcbuild.harness;

import com.google.gson.GsonBuilder;
import com.google.gson.JsonArray;
import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
import fi.dy.masa.litematica.config.Configs;
import fi.dy.masa.litematica.schematic.LitematicaSchematic;
import fi.dy.masa.litematica.schematic.placement.SchematicPlacement;
import fi.dy.masa.litematica.util.ReplaceBehavior;
import fi.dy.masa.malilib.config.IConfigOptionListEntry;
import net.fabricmc.fabric.api.client.gametest.v1.FabricClientGameTest;
import net.fabricmc.fabric.api.client.gametest.v1.context.ClientGameTestContext;
import net.fabricmc.fabric.impl.client.gametest.world.TestWorldSaveImpl;
import net.minecraft.block.BlockState;
import net.minecraft.client.option.Perspective;
import net.minecraft.registry.Registries;
import net.minecraft.server.world.ServerWorld;
import net.minecraft.state.property.Property;
import net.minecraft.util.math.BlockPos;

import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.*;

/**
 * Real-client acceptance test, configured by the JSON file named in -Dmcbuild.config (written by `mcb ingame`):
 * the user's own Litematica reads the delivered .litematic, pastes it with its own placement code into a vanilla
 * save holding the site terrain (once per paste mode), every schematic cell is compared with the world, and the
 * vanilla renderer takes the listed screenshots. Results go to outDir/ingame-report.json.
 */
public final class IngameTest implements FabricClientGameTest {
    static <T extends Comparable<T>> String value(BlockState s, Property<T> p) { return p.name(s.get(p)); }

    static String key(BlockState s) {
        String name = Registries.BLOCK.getId(s.getBlock()).toString();
        TreeMap<String, String> props = new TreeMap<>();
        for (Property<?> p : s.getProperties()) props.put(p.getName(), value(s, p));
        if (props.isEmpty()) return name;
        StringJoiner j = new StringJoiner(",", "[", "]");
        props.forEach((k, v) -> j.add(k + "=" + v));
        return name + j;
    }

    static ReplaceBehavior mode(String name, ReplaceBehavior fallback) {
        return switch (name.toLowerCase(Locale.ROOT)) {
            case "none" -> ReplaceBehavior.NONE;
            case "all" -> ReplaceBehavior.ALL;
            case "with_non_air", "non_air" -> ReplaceBehavior.WITH_NON_AIR;
            default -> fallback;
        };
    }

    static int[] ints(JsonElement e) {
        JsonArray a = e.getAsJsonArray(); int[] out = new int[a.size()];
        for (int i = 0; i < out.length; i++) out[i] = a.get(i).getAsInt();
        return out;
    }

    @Override
    public void runTest(ClientGameTestContext context) {
        String cfgPath = System.getProperty("mcbuild.config");
        if (cfgPath == null) throw new AssertionError("missing -Dmcbuild.config");
        JsonObject cfg;
        try { cfg = JsonParser.parseString(Files.readString(Path.of(cfgPath), StandardCharsets.UTF_8)).getAsJsonObject(); }
        catch (Exception e) { throw new RuntimeException(e); }
        Path out = Path.of(cfg.get("outDir").getAsString());
        Map<String, Object> report = new LinkedHashMap<>();
        try {
            Files.createDirectories(out);
            context.runOnClient(client -> {
                client.options.hudHidden = true;
                client.options.getFov().setValue(cfg.has("fov") ? cfg.get("fov").getAsInt() : 80);
                client.options.getViewDistance().setValue(cfg.has("viewDistance") ? cfg.get("viewDistance").getAsInt() : 16);
                client.options.getSimulationDistance().setValue(8);
                client.options.setPerspective(Perspective.FIRST_PERSON);
                client.options.getGamma().setValue(cfg.has("gamma") ? cfg.get("gamma").getAsDouble() : 0.5);
            });
            try (var world = new TestWorldSaveImpl(context, Path.of("saves", cfg.get("save").getAsString())).open()) {
                var server = world.getServer();
                context.waitTicks(40);
                server.runCommand("gamemode spectator @a");
                server.runCommand("time set " + (cfg.has("time") ? cfg.get("time").getAsInt() : 1000));
                if (cfg.has("forceload")) {
                    int[] f = ints(cfg.get("forceload"));
                    server.runCommand("forceload add " + f[0] + " " + f[1] + " " + f[2] + " " + f[3]);
                }
                context.waitTicks(cfg.has("settle") ? cfg.get("settle").getAsInt() : 60);
                if (cfg.has("schematicFile")) {
                    List<String> lines = Files.readAllLines(Path.of(cfg.get("expected").getAsString()));
                    int[] o = ints(cfg.get("origin"));
                    BlockPos origin = new BlockPos(o[0], o[1], o[2]);
                    List<String> modes = new ArrayList<>();
                    for (JsonElement m : cfg.getAsJsonArray("modes")) modes.add(m.getAsString());
                    server.runOnServer(game -> {
                        ServerWorld w = game.getOverworld();
                        LitematicaSchematic schematic = LitematicaSchematic.createFromFile(Path.of(cfg.get("schematicDir").getAsString()),
                                cfg.get("schematicFile").getAsString());
                        if (schematic == null) throw new AssertionError("Litematica could not read the schematic");
                        report.put("litematicaRegions", schematic.getSubRegionCount());
                        report.put("litematicaMetadataTotalBlocks", schematic.getMetadata().getTotalBlocks());
                        report.put("litematicaMetadataName", schematic.getMetadata().getName());
                        SchematicPlacement placement = SchematicPlacement.createFor(schematic, origin, "mcbuild", true, true);
                        IConfigOptionListEntry previous = Configs.Generic.PASTE_REPLACE_BEHAVIOR.getOptionListValue();
                        report.put("defaultPasteReplaceBehavior", previous.getStringValue());
                        for (String name : modes) {
                            ReplaceBehavior mode = mode(name, (ReplaceBehavior) previous);
                            Configs.Generic.PASTE_REPLACE_BEHAVIOR.setOptionListValue(mode);
                            if (!schematic.placeToWorld(w, placement, false)) throw new AssertionError("placeToWorld returned false for " + mode);
                            int checked = 0, mismatched = 0, blockEntities = 0;
                            Map<String, Integer> kinds = new TreeMap<>();
                            List<String> examples = new ArrayList<>();
                            for (String line : lines) {
                                if (line.isBlank()) continue;
                                String[] f = line.split(" ", 4);
                                BlockPos pos = new BlockPos(Integer.parseInt(f[0]), Integer.parseInt(f[1]), Integer.parseInt(f[2]));
                                String got = key(w.getBlockState(pos));
                                checked++;
                                if (!got.equals(f[3])) {
                                    mismatched++;
                                    kinds.merge(f[3].split("\\[")[0] + " <- " + got.split("\\[")[0], 1, Integer::sum);
                                    if (examples.size() < 12) examples.add(line + "  ->  " + got);
                                }
                                if (w.getBlockEntity(pos) != null && !f[3].equals("minecraft:air")) blockEntities++;
                            }
                            Map<String, Object> r = new LinkedHashMap<>();
                            r.put("cellsChecked", checked); r.put("cellsMismatched", mismatched); r.put("mismatchKinds", kinds);
                            r.put("examples", examples); r.put("blockEntitiesPresent", blockEntities);
                            report.put("paste_" + name + "(" + mode.getStringValue() + ")", r);
                            report.put("cellsMismatched", mismatched);
                        }
                        Configs.Generic.PASTE_REPLACE_BEHAVIOR.setOptionListValue(previous);
                    });
                }
                List<String> shots = new ArrayList<>();
                Integer lastTime = null;
                for (JsonElement e : cfg.getAsJsonArray("views")) {
                    JsonObject v = e.getAsJsonObject();
                    if (v.has("fov")) { int fov = Math.max(30, Math.min(110, Math.round(v.get("fov").getAsFloat())));
                        context.runOnClient(client -> client.options.getFov().setValue(fov)); }
                    int t = v.has("time") ? v.get("time").getAsInt() : 1000;
                    if (lastTime == null || t != lastTime) { server.runCommand("time set " + t); lastTime = t; }
                    JsonArray p = v.getAsJsonArray("pos");
                    server.runCommand(String.format(Locale.ROOT, "tp @a %.3f %.3f %.3f %.3f %.3f", p.get(0).getAsDouble(), p.get(1).getAsDouble(),
                            p.get(2).getAsDouble(), v.get("yaw").getAsDouble(), v.get("pitch").getAsDouble()));
                    context.waitTicks(v.has("wait") ? v.get("wait").getAsInt() : 40);
                    world.getClientWorld().waitForChunksRender(false, 2400);
                    context.waitTicks(30);
                    String name = v.get("name").getAsString();
                    Files.copy(context.takeScreenshot(name), out.resolve(name + ".png"), StandardCopyOption.REPLACE_EXISTING);
                    shots.add(name + ".png");
                }
                report.put("screenshots", shots);
            }
            report.put("status", ((Number) report.getOrDefault("cellsMismatched", 0)).intValue() == 0 ? "PASS" : "MISMATCH");
            Files.writeString(out.resolve("ingame-report.json"), new GsonBuilder().setPrettyPrinting().create().toJson(report));
        } catch (Throwable e) {
            try { Files.createDirectories(out); Files.writeString(out.resolve("FAILED.txt"), e + "\n" + report); } catch (Exception ignored) { }
            throw new RuntimeException(e);
        }
    }
}
