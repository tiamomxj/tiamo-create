// Independent read-only RocksDB bridge for Voxy caches. No Voxy code is linked or copied.
import java.io.*;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.util.*;
import org.rocksdb.*;

public final class AtlasVoxyReader {
    static byte[] key(long value) { return ByteBuffer.allocate(8).putLong(value).array(); }
    static void blob(DataOutputStream out, byte[] value) throws IOException {
        out.writeInt(value == null ? -1 : value.length);
        if (value != null) out.write(value);
    }
    public static void main(String[] args) throws Exception {
        RocksDB.loadLibrary();
        List<ColumnFamilyHandle> handles = new ArrayList<>();
        List<ColumnFamilyOptions> cfOptions = new ArrayList<>();
        try (Options listing = new Options(); DBOptions options = new DBOptions().setCreateIfMissing(false).setMaxOpenFiles(64);
             Cache cache = new LRUCache(24L * 1024 * 1024)) {
            var names = RocksDB.listColumnFamilies(listing, args[0]);
            List<ColumnFamilyDescriptor> descriptors = new ArrayList<>();
            for (byte[] name : names) {
                var cf = new ColumnFamilyOptions().setTableFormatConfig(new BlockBasedTableConfig().setBlockCache(cache));
                cfOptions.add(cf); descriptors.add(new ColumnFamilyDescriptor(name, cf));
            }
            try (RocksDB db = RocksDB.openReadOnly(options, args[0], descriptors, handles, false)) {
              try {
                ColumnFamilyHandle sections = null, mappings = null;
                for (int i=0;i<names.size();i++) {
                    String name = new String(names.get(i), StandardCharsets.UTF_8);
                    if (name.equals("world_sections")) sections = handles.get(i);
                    if (name.equals("id_mappings")) mappings = handles.get(i);
                }
                if (sections == null || mappings == null) throw new IOException("Missing Voxy column families");
                var in = new DataInputStream(new BufferedInputStream(System.in));
                var out = new DataOutputStream(new BufferedOutputStream(System.out));
                out.writeInt(0x41545658); out.flush();
                while (true) {
                    int cmd;
                    try { cmd = in.readUnsignedByte(); } catch (EOFException end) { break; }
                    if (cmd == 0) break;
                    var buffer = new ByteArrayOutputStream(); var data = new DataOutputStream(buffer);
                    try {
                        if (cmd == 1) { // Highest available level, and only its keys.
                            try (RocksIterator it = db.newIterator(sections)) {
                                it.seekToLast(); int level = it.isValid() ? (it.key()[0] & 255) >>> 4 : -1;
                                data.writeInt(level);
                                if (level >= 0) {
                                    it.seek(key((long) level << 60));
                                    while (it.isValid() && ((it.key()[0] & 255) >>> 4) == level) {
                                        data.write(it.key()); it.next();
                                    }
                                }
                            }
                        } else if (cmd == 2) { // Batched independent point lookups.
                            int count = in.readInt();
                            if (count < 0 || count > 4096) throw new IOException("Invalid key count");
                            for (int i=0;i<count;i++) { byte[] k = new byte[8]; in.readFully(k); blob(data, db.get(sections,k)); }
                        } else if (cmd == 3) {
                            try (RocksIterator it = db.newIterator(mappings)) {
                                for (it.seekToFirst();it.isValid();it.next()) { data.write(it.key()); blob(data,it.value()); }
                            }
                        } else throw new IOException("Unknown read command");
                        blob(out, buffer.toByteArray());
                    } catch (Exception error) {
                        out.writeInt(-2); blob(out,error.toString().getBytes(StandardCharsets.UTF_8));
                    }
                    out.flush();
                }
              } finally {
                for (ColumnFamilyHandle handle : handles) handle.close();
                handles.clear();
              }
            } finally {
                for (ColumnFamilyHandle handle : handles) handle.close();
                for (ColumnFamilyOptions option : cfOptions) option.close();
            }
        }
    }
}
