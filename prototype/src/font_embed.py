"""Embed TrueType fonts inside a PPTX file so it renders on any machine
without requiring the font to be installed locally.

This is the only reliable fix for Tamil/Indic glyphs in PPTX deliverables.
The complex-script typeface fix (D9) is necessary but not sufficient: it
tells PowerPoint *which* font to use for Tamil glyphs, but the viewer's
machine still has to have that font. With embedding, the font travels
inside the .pptx and PowerPoint pulls glyphs from there.

OOXML reference: ECMA-376 Part 1, §14.2.4.5 "embeddedFont" + §17.16.5 on
the obfuscation algorithm.
"""
from __future__ import annotations
import shutil
import uuid
import zipfile
from pathlib import Path

from lxml import etree


_NS_P = "http://schemas.openxmlformats.org/presentationml/2006/main"
_NS_R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_NS_CT = "http://schemas.openxmlformats.org/package/2006/content-types"
_NS_PR = "http://schemas.openxmlformats.org/package/2006/relationships"
_NSMAP_PRES = {"p": _NS_P, "r": _NS_R}

# Relationship type for embedded fonts.
_REL_FONT = (
    "http://schemas.openxmlformats.org/officeDocument/2006/relationships/font"
)
# Content-type for the obfuscated font binary.
_CT_FONT = "application/vnd.openxmlformats-officedocument.obfuscatedFont"


def _obfuscate_font(font_bytes: bytes, guid_bytes_le: bytes) -> bytes:
    """Obfuscate font per ECMA-376: XOR the first 32 bytes with the GUID
    bytes (little-endian), repeating the GUID twice.

    PowerPoint refuses to load a non-obfuscated font binary even though the
    obfuscation provides zero security — it's a license-attribution token,
    not a cipher.
    """
    if len(font_bytes) < 32:
        return font_bytes
    obf = bytearray(font_bytes)
    for i in range(32):
        # Pattern: byte i XOR guid_bytes_le[15 - (i % 16)]
        obf[i] ^= guid_bytes_le[15 - (i % 16)]
    return bytes(obf)


def _guid_braces(u: uuid.UUID) -> str:
    """Render a GUID in the {XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX} form
    that OOXML requires for embedded-font GUIDs."""
    return "{" + str(u).upper() + "}"


def embed_fonts_in_pptx(
    pptx_path: str,
    typeface: str,
    regular_ttf: Path,
    bold_ttf: Path | None = None,
) -> None:
    """Embed a TTF (optionally a bold variant) into the PPTX at `pptx_path`.

    Mutates the file in place. Safe to call on a freshly-saved python-pptx
    file — we rewrite the zip with the additions and replace the original.
    """
    pptx = Path(pptx_path)
    if not pptx.exists():
        raise FileNotFoundError(pptx)
    regular_ttf = Path(regular_ttf)
    if bold_ttf is not None:
        bold_ttf = Path(bold_ttf)

    # Generate one GUID per font face. Same GUID is used both as the
    # obfuscation key AND as the identifier inside <p:font>.
    regular_uuid = uuid.uuid4()
    regular_obf = _obfuscate_font(
        regular_ttf.read_bytes(), regular_uuid.bytes_le
    )

    bold_uuid = None
    bold_obf = None
    if bold_ttf is not None and bold_ttf.exists():
        bold_uuid = uuid.uuid4()
        bold_obf = _obfuscate_font(bold_ttf.read_bytes(), bold_uuid.bytes_le)

    temp = pptx.with_suffix(pptx.suffix + ".embed.tmp")
    if temp.exists():
        temp.unlink()

    with zipfile.ZipFile(pptx, "r") as src, zipfile.ZipFile(
        temp, "w", zipfile.ZIP_DEFLATED
    ) as dst:
        rewrite = {
            "[Content_Types].xml",
            "ppt/presentation.xml",
            "ppt/_rels/presentation.xml.rels",
        }

        # Pass through everything we don't touch
        for name in src.namelist():
            if name in rewrite:
                continue
            dst.writestr(name, src.read(name))

        # Add obfuscated font binaries at fixed paths
        dst.writestr("ppt/fonts/font1.fntdata", regular_obf)
        if bold_obf is not None:
            dst.writestr("ppt/fonts/font2.fntdata", bold_obf)

        # 1. Update [Content_Types].xml to declare the fntdata extension
        ct_bytes = src.read("[Content_Types].xml")
        ct_root = etree.fromstring(ct_bytes)
        has_fntdata = any(
            d.get("Extension") == "fntdata"
            for d in ct_root.findall(f"{{{_NS_CT}}}Default")
        )
        if not has_fntdata:
            d = etree.SubElement(ct_root, f"{{{_NS_CT}}}Default")
            d.set("Extension", "fntdata")
            d.set("ContentType", _CT_FONT)
        dst.writestr(
            "[Content_Types].xml",
            etree.tostring(
                ct_root, xml_declaration=True, encoding="UTF-8",
                standalone=True,
            ),
        )

        # 2. Update presentation rels to reference the embedded fonts
        rels_bytes = src.read("ppt/_rels/presentation.xml.rels")
        rels_root = etree.fromstring(rels_bytes)
        max_rid = 0
        for rel in rels_root.findall(f"{{{_NS_PR}}}Relationship"):
            rid = rel.get("Id", "")
            if rid.startswith("rId"):
                try:
                    max_rid = max(max_rid, int(rid[3:]))
                except ValueError:
                    pass

        regular_rid = f"rId{max_rid + 1}"
        r1 = etree.SubElement(rels_root, f"{{{_NS_PR}}}Relationship")
        r1.set("Id", regular_rid)
        r1.set("Type", _REL_FONT)
        r1.set("Target", "fonts/font1.fntdata")

        bold_rid: str | None = None
        if bold_obf is not None:
            bold_rid = f"rId{max_rid + 2}"
            r2 = etree.SubElement(rels_root, f"{{{_NS_PR}}}Relationship")
            r2.set("Id", bold_rid)
            r2.set("Type", _REL_FONT)
            r2.set("Target", "fonts/font2.fntdata")

        dst.writestr(
            "ppt/_rels/presentation.xml.rels",
            etree.tostring(
                rels_root, xml_declaration=True, encoding="UTF-8",
                standalone=True,
            ),
        )

        # 3. Add <p:embeddedFontLst> to presentation.xml
        pres_bytes = src.read("ppt/presentation.xml")
        pres_root = etree.fromstring(pres_bytes)

        # Strip any existing list so we don't double-embed
        for old in pres_root.findall(f"{{{_NS_P}}}embeddedFontLst"):
            pres_root.remove(old)

        emb_list = etree.Element(f"{{{_NS_P}}}embeddedFontLst")
        emb_font = etree.SubElement(emb_list, f"{{{_NS_P}}}embeddedFont")

        font_el = etree.SubElement(emb_font, f"{{{_NS_P}}}font")
        font_el.set("typeface", typeface)
        # panose: tell PowerPoint this is a generic sans font; the value
        # below is a safe default for sans-serif-Latin/Indic.
        font_el.set("panose", "020B0604020202020204")
        font_el.set("pitchFamily", "34")
        font_el.set("charset", "0")

        reg_el = etree.SubElement(emb_font, f"{{{_NS_P}}}regular")
        reg_el.set(f"{{{_NS_R}}}id", regular_rid)
        if bold_rid is not None:
            bold_el = etree.SubElement(emb_font, f"{{{_NS_P}}}bold")
            bold_el.set(f"{{{_NS_R}}}id", bold_rid)

        # OOXML schema dictates: embeddedFontLst goes after sldIdLst /
        # sldSz / notesSz / smartTags and before custShowLst /
        # photoAlbum / kinsoku / defaultTextStyle / modifyVerifier / extLst.
        # Insert just before the first "after" sibling we find.
        after_tags = {
            f"{{{_NS_P}}}custShowLst",
            f"{{{_NS_P}}}photoAlbum",
            f"{{{_NS_P}}}kinsoku",
            f"{{{_NS_P}}}defaultTextStyle",
            f"{{{_NS_P}}}modifyVerifier",
            f"{{{_NS_P}}}extLst",
        }
        insert_idx: int | None = None
        for i, child in enumerate(pres_root):
            if child.tag in after_tags:
                insert_idx = i
                break
        if insert_idx is None:
            pres_root.append(emb_list)
        else:
            pres_root.insert(insert_idx, emb_list)

        dst.writestr(
            "ppt/presentation.xml",
            etree.tostring(
                pres_root, xml_declaration=True, encoding="UTF-8",
                standalone=True,
            ),
        )

    shutil.move(str(temp), str(pptx))
