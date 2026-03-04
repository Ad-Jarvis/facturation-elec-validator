import io
import tempfile
from pathlib import Path

import pandas as pd
import streamlit as st
from lxml import etree
from saxonche import PySaxonProcessor

SVRL_NS = {"svrl": "http://purl.oclc.org/dsdl/svrl"}

st.set_page_config(page_title="Validation Schematron (EXTENDED CTC FR)", layout="wide")

st.title("Validation Schematron (EXTENDED-CTC-FR) — UBL/CII")
st.write("Charge un **XML** et un fichier de règles **XSL** (schématron compilé), puis lance la validation. "
         "Le rapport produit est un **SVRL**.")

col1, col2 = st.columns(2)
with col1:
    xml_file = st.file_uploader("Fichier XML à valider", type=["xml"])
with col2:
    xsl_file = st.file_uploader("Fichier de règles (XSL / XSLT)", type=["xsl", "xslt"])

run = st.button(" Valider", type="primary", disabled=not (xml_file and xsl_file))

def run_validation(xml_path: Path, xsl_path: Path) -> str:
    with PySaxonProcessor(license=False) as proc:
        xslt30 = proc.new_xslt30_processor()
        executable = xslt30.compile_stylesheet(
            stylesheet_file=str(xsl_path),
            base_uri=xsl_path.parent.as_uri()  
        )
        return executable.transform_to_string(source_file=str(xml_path))

def parse_svrl(svrl_xml: str) -> pd.DataFrame:
    root = etree.fromstring(svrl_xml.encode("utf-8"))
    failed = root.xpath("//svrl:failed-assert", namespaces=SVRL_NS)

    rows = []
    for fa in failed:
        flag = (fa.get("flag") or "").lower()
        rule_id = fa.get("id") or ""
        msg = "".join(fa.xpath("string(svrl:text)", namespaces=SVRL_NS)).strip()
        rows.append({"severity": flag or "info", "id": rule_id, "message": msg})

    # tri: fatal/error puis warning puis le reste
    order = {"fatal": 0, "error": 1, "warning": 2}
    rows.sort(key=lambda r: (order.get(r["severity"], 9), r["id"]))
    return pd.DataFrame(rows)

if run:
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)

            xml_path = tmpdir / "input.xml"
            xsl_path = tmpdir / "rules.xsl"

            xml_path.write_bytes(xml_file.getvalue())
            xsl_path.write_bytes(xsl_file.getvalue())

            with st.spinner("Validation en cours..."):
                svrl = run_validation(xml_path, xsl_path)

            df = parse_svrl(svrl)

            fatals = int((df["severity"].isin(["fatal", "error"])).sum()) if not df.empty else 0
            warns = int((df["severity"] == "warning").sum()) if not df.empty else 0

            c1, c2, c3 = st.columns(3)
            c1.metric("Fatals / Errors", fatals)
            c2.metric("Warnings", warns)
            c3.metric("Total failed-assert", len(df))

            st.subheader("Résultats")
            if df.empty:
                st.success("Aucune erreur (failed-assert). Conforme selon ce jeu de règles.")
            else:
                st.dataframe(df, use_container_width=True, height=420)

            st.subheader("Téléchargements")
            st.download_button(
                " Télécharger le rapport SVRL (XML)",
                data=svrl.encode("utf-8"),
                file_name="report_svrl.xml",
                mime="application/xml",
            )
            if not df.empty:
                csv_bytes = df.to_csv(index=False).encode("utf-8")
                st.download_button(
                    " Télécharger le détail (CSV)",
                    data=csv_bytes,
                    file_name="report_summary.csv",
                    mime="text/csv",
                )

    except Exception as e:
        st.error(f"Échec de la validation : {e}")