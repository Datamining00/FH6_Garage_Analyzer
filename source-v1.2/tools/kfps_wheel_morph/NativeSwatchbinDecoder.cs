using System.Security.Cryptography;
using ForzaTools.Bundles;
using ForzaTools.Bundles.Blobs;
using ForzaTools.Bundles.Metadata;
using ForzaTools.Bundles.Metadata.TextureContentHeaders;

namespace Kfps.ChassisConverter;

internal sealed record NativeSwatchbinDecodeDiagnostic(
    string Status,
    string Input,
    string Output,
    uint Width,
    uint Height,
    uint Depth,
    int MipLevels,
    bool IsTextureCube,
    bool IsTexture3D,
    bool IsPremultipliedAlpha,
    bool IsDurangoFormat,
    int Encoding,
    int Transcoding,
    int ColorProfile,
    uint DxgiFormat,
    string DxgiFormatName,
    int RawTextureBytes,
    int DdsBytes,
    string InputSha256,
    string DdsSha256,
    bool GameDataModified);

internal static class NativeSwatchbinDecoder
{
    public static NativeSwatchbinDecodeDiagnostic Decode(string inputValue, string outputValue)
    {
        var input = Path.GetFullPath(inputValue);
        var output = Path.GetFullPath(outputValue);
        if (!File.Exists(input))
            throw new FileNotFoundException("The native swatchbin payload does not exist.", input);
        if (string.Equals(input, output, StringComparison.OrdinalIgnoreCase))
            throw new InvalidDataException("Swatchbin decode output must not overwrite the source payload.");

        var bundle = new Bundle();
        using (var stream = File.OpenRead(input))
            bundle.Load(stream);

        var textureBlob = bundle.Blobs.OfType<TextureContentBlob>().FirstOrDefault()
            ?? throw new InvalidDataException("No TXCB (Texture Content Blob) was found in the swatchbin payload.");
        var headerMetadata = textureBlob.GetMetadataByTag<TextureContentHeaderMetadata>(
            BundleMetadata.TAG_METADATA_TextureContentHeader)
            ?? throw new InvalidDataException("No TXCH (Texture Content Header) metadata was found in the swatchbin payload.");
        headerMetadata.ParseWithBlobVersion(textureBlob.VersionMajor, textureBlob.VersionMinor);

        uint width;
        uint height;
        uint depth;
        int mipLevels;
        bool isCube;
        bool is3D;
        bool premultiplied;
        bool isDurango;
        int encoding;
        int transcoding;
        int colorProfile;

        if (headerMetadata.PCHeader is PCTextureContentHeader pc)
        {
            width = pc.Width;
            height = pc.Height;
            depth = pc.Depth;
            mipLevels = pc.NumMips;
            isCube = pc.IsCubeMap;
            is3D = false;
            premultiplied = pc.IsPremultipliedAlpha;
            isDurango = false;
            encoding = pc.Slices.Count > 0 ? (int)pc.Slices[0].Encoding : -1;
            transcoding = (int)pc.Transcoding;
            colorProfile = (int)pc.TargetColorProfile;
        }
        else if (headerMetadata.DurangoHeader is DurangoTextureContentHeader durango)
        {
            width = durango.Width;
            height = durango.Height;
            depth = durango.Depth;
            mipLevels = durango.NumMips;
            isCube = durango.IsCubeMap;
            is3D = durango.Is3DTexture;
            premultiplied = durango.IsPremultipliedAlpha;
            isDurango = true;
            encoding = (int)durango.Encoding;
            transcoding = (int)durango.Transcoding;
            colorProfile = (int)durango.TargetColorProfile;
        }
        else
        {
            throw new InvalidDataException("The TXCH header is neither PC nor Durango format.");
        }

        // ForzaTechStudio's reference renderer detiles and dealigns Durango/Xbox
        // swatchbin texture memory through the XG resource-layout API before DDS
        // construction. This standalone helper does not carry that native XG
        // dependency. Never label tiled bytes as a linear render-ready DDS.
        if (isDurango)
            throw new InvalidDataException(
                "Durango/Xbox swatchbin decoding requires XG detile/dealign before DDS construction; refusing to wrap tiled texture bytes as linear DDS.");

        var raw = textureBlob.Data;
        if (raw is null || raw.Length == 0)
            throw new InvalidDataException("The TXCB blob contains no texture bytes.");
        if (width == 0 || height == 0 || mipLevels <= 0)
            throw new InvalidDataException("The native texture header has invalid dimensions or mip count.");

        var dxgi = GetDxgiFormat(encoding, transcoding, colorProfile);
        if (dxgi == 0)
            throw new InvalidDataException(
                $"Unsupported native texture encoding/transcoding combination: encoding={encoding}, transcoding={transcoding}, colorProfile={colorProfile}.");

        var dds = CreateDds(
            width,
            height,
            depth,
            mipLevels,
            isCube,
            is3D,
            dxgi,
            raw);

        Directory.CreateDirectory(Path.GetDirectoryName(output)!);
        var temporary = output + $".{Environment.ProcessId}.tmp";
        try
        {
            File.WriteAllBytes(temporary, dds);
            File.Move(temporary, output, true);
        }
        finally
        {
            try { File.Delete(temporary); } catch { }
        }

        return new NativeSwatchbinDecodeDiagnostic(
            "decoded_dds",
            input,
            output,
            width,
            height,
            depth,
            mipLevels,
            isCube,
            is3D,
            premultiplied,
            isDurango,
            encoding,
            transcoding,
            colorProfile,
            dxgi,
            GetDxgiFormatName(dxgi),
            raw.Length,
            dds.Length,
            Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(input))).ToLowerInvariant(),
            Convert.ToHexString(SHA256.HashData(dds)).ToLowerInvariant(),
            false);
    }

    private static byte[] CreateDds(
        uint width,
        uint height,
        uint depth,
        int mipLevels,
        bool isCube,
        bool is3D,
        uint dxgiFormat,
        byte[] textureData)
    {
        using var stream = new MemoryStream();
        using var writer = new BinaryWriter(stream);

        writer.Write(0x20534444u); // DDS magic
        writer.Write(124u);
        writer.Write(0x000A1007u); // CAPS | HEIGHT | WIDTH | PIXELFORMAT | MIPMAPCOUNT | LINEARSIZE
        writer.Write(height);
        writer.Write(width);
        writer.Write(CalculateLinearSize(width, height, dxgiFormat));
        writer.Write(depth > 1 ? depth : 1u);
        writer.Write((uint)mipLevels);
        for (var i = 0; i < 11; i++) writer.Write(0u);

        writer.Write(32u);       // DDS_PIXELFORMAT size
        writer.Write(0x4u);     // FOURCC
        writer.Write(0x30315844u); // DX10
        writer.Write(0u);
        writer.Write(0u);
        writer.Write(0u);
        writer.Write(0u);
        writer.Write(0u);

        var caps = 0x1000u;
        if (mipLevels > 1) caps |= 0x400008u;
        writer.Write(caps);
        writer.Write(isCube ? 0xFE00u : 0u);
        writer.Write(0u);
        writer.Write(0u);
        writer.Write(0u);

        writer.Write(dxgiFormat);
        writer.Write(is3D ? 4u : 3u); // D3D10_RESOURCE_DIMENSION_TEXTURE3D/TEXTURE2D
        writer.Write(isCube ? 0x4u : 0u);
        writer.Write(1u);
        writer.Write(0u);
        writer.Write(textureData);
        return stream.ToArray();
    }

    private static uint CalculateLinearSize(uint width, uint height, uint dxgiFormat)
    {
        var blockSize = GetBlockSize(dxgiFormat);
        if (blockSize > 0)
        {
            var blocksWide = Math.Max(1u, (width + 3) / 4);
            var blocksHigh = Math.Max(1u, (height + 3) / 4);
            return blocksWide * blocksHigh * blockSize;
        }
        var bitsPerPixel = GetBitsPerPixel(dxgiFormat);
        return ((width * bitsPerPixel + 7) / 8) * height;
    }

    private static uint GetBlockSize(uint dxgiFormat) => dxgiFormat switch
    {
        71 or 72 => 8,
        74 or 75 => 16,
        77 or 78 => 16,
        80 or 81 => 8,
        83 or 84 => 16,
        95 or 96 => 16,
        98 or 99 => 16,
        _ => 0,
    };

    private static uint GetBitsPerPixel(uint dxgiFormat) => dxgiFormat switch
    {
        2 => 128,
        10 or 11 => 64,
        28 or 29 or 87 => 32,
        49 or 85 or 86 => 16,
        61 or 65 => 8,
        _ => 32,
    };

    private static uint GetDxgiFormat(int encoding, int transcoding, int colorProfile)
    {
        var isSrgb = colorProfile == 1; // Rec709SRgb
        var formatEncoded = transcoding <= 1 ? encoding : transcoding - 2;
        return formatEncoded switch
        {
            0 => isSrgb ? 72u : 71u,
            1 => isSrgb ? 75u : 74u,
            2 => isSrgb ? 78u : 77u,
            3 => 80u,
            4 => 81u,
            5 => 83u,
            6 => 84u,
            7 => 95u,
            8 => 96u,
            9 => isSrgb ? 99u : 98u,
            10 => 2u,
            11 => 11u,
            12 => 10u,
            13 => isSrgb ? 29u : 28u,
            14 => 85u,
            15 => 86u,
            19 => 61u,
            20 => 65u,
            21 => 49u,
            22 => isSrgb ? 99u : 98u,
            _ => 0u,
        };
    }

    private static string GetDxgiFormatName(uint format) => format switch
    {
        2 => "DXGI_FORMAT_R32G32B32A32_FLOAT",
        10 => "DXGI_FORMAT_R16G16B16A16_FLOAT",
        11 => "DXGI_FORMAT_R16G16B16A16_UNORM",
        28 => "DXGI_FORMAT_R8G8B8A8_UNORM",
        29 => "DXGI_FORMAT_R8G8B8A8_UNORM_SRGB",
        49 => "DXGI_FORMAT_R8G8_UNORM",
        61 => "DXGI_FORMAT_R8_UNORM",
        65 => "DXGI_FORMAT_A8_UNORM",
        71 => "DXGI_FORMAT_BC1_UNORM",
        72 => "DXGI_FORMAT_BC1_UNORM_SRGB",
        74 => "DXGI_FORMAT_BC2_UNORM",
        75 => "DXGI_FORMAT_BC2_UNORM_SRGB",
        77 => "DXGI_FORMAT_BC3_UNORM",
        78 => "DXGI_FORMAT_BC3_UNORM_SRGB",
        80 => "DXGI_FORMAT_BC4_UNORM",
        81 => "DXGI_FORMAT_BC4_SNORM",
        83 => "DXGI_FORMAT_BC5_UNORM",
        84 => "DXGI_FORMAT_BC5_SNORM",
        85 => "DXGI_FORMAT_B5G6R5_UNORM",
        86 => "DXGI_FORMAT_B5G5R5A1_UNORM",
        87 => "DXGI_FORMAT_B8G8R8A8_UNORM",
        95 => "DXGI_FORMAT_BC6H_UF16",
        96 => "DXGI_FORMAT_BC6H_SF16",
        98 => "DXGI_FORMAT_BC7_UNORM",
        99 => "DXGI_FORMAT_BC7_UNORM_SRGB",
        _ => "DXGI_FORMAT_UNKNOWN",
    };
}
