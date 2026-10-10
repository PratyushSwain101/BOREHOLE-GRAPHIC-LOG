import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from matplotlib.backends.backend_pdf import PdfPages
from mpl_toolkits.axes_grid1 import make_axes_locatable
import io

st.set_page_config(page_title="Geological Graphic Log Generator", layout="wide")

st.title("📊 Geological Graphic Log Generator")
st.markdown("Upload collar, lithology, and boundary CSV files.")

# Initialize Session State
if "generated_pdf" not in st.session_state:
    st.session_state.generated_pdf = None
if "pdf_filename" not in st.session_state:
    st.session_state.pdf_filename = ""


def preprocess_litho(litho_df, max_gap_meters=2.0):
    """Clean lithology data and merge consecutively occurring identical seams."""
    litho_df = litho_df.copy()
    litho_df.columns = [c.strip().upper() for c in litho_df.columns]
    
    litho_df['SEAM'] = litho_df['SEAM'].fillna('').astype(str).str.strip()
    litho_df['LITHOLOGY'] = litho_df['LITHOLOGY'].fillna('').astype(str).str.strip()
    
    merged_seams = []
    
    for bore_id, group in litho_df.groupby('BORE ID', sort=False):
        group = group.sort_values('FROM').reset_index(drop=True)
        
        curr_seam = None
        curr_from = None
        curr_to = None
        
        for _, row in group.iterrows():
            seam = row['SEAM']
            from_d = float(row['FROM'])
            to_d = float(row['TO'])
            
            if seam != '' and seam.lower() != 'nan':
                if curr_seam == seam:
                    gap = from_d - curr_to
                    if gap <= max_gap_meters:
                        curr_to = to_d
                    else:
                        merged_seams.append({
                            'BORE ID': bore_id,
                            'SEAM': curr_seam,
                            'FROM': curr_from,
                            'TO': curr_to,
                            'THICKNESS': round(curr_to - curr_from, 2)
                        })
                        curr_seam = seam
                        curr_from = from_d
                        curr_to = to_d
                else:
                    if curr_seam is not None:
                        merged_seams.append({
                            'BORE ID': bore_id,
                            'SEAM': curr_seam,
                            'FROM': curr_from,
                            'TO': curr_to,
                            'THICKNESS': round(curr_to - curr_from, 2)
                        })
                    curr_seam = seam
                    curr_from = from_d
                    curr_to = to_d
                    
        if curr_seam is not None:
            merged_seams.append({
                'BORE ID': bore_id,
                'SEAM': curr_seam,
                'FROM': curr_from,
                'TO': curr_to,
                'THICKNESS': round(curr_to - curr_from, 2)
            })
            
    return pd.DataFrame(merged_seams)


def get_page_dimensions(size, orientation):
    """Return width and height in inches for given page size and orientation."""
    dims = {
        "A4": (8.27, 11.69),
        "A3": (11.69, 16.54),
        "A2": (16.54, 23.39)
    }
    w, h = dims.get(size, (11.69, 16.54))
    if orientation == "Landscape":
        return max(w, h), min(w, h)
    else:
        return min(w, h), max(w, h)


def create_graphic_logs_pdf(collar_df, litho_df, merged_seams_df, bh_list, page_size, page_orientation, scale_option, scale_meters_per_cm, col_width_cm, max_boreholes_per_page=5):
    """
    Generate PDF containing borehole graphic logs strictly honoring exact physical column width
    and vertical depth scaling without stretching.
    """
    pdf_buffer = io.BytesIO()
    page_w_in, page_h_in = get_page_dimensions(page_size, page_orientation)
    
    col_width_in = col_width_cm / 2.54
    header_height_in = 1.2
    top_margin_in = 1.0
    bottom_margin_in = 0.8
    
    printable_h_in = page_h_in - top_margin_in - header_height_in - bottom_margin_in
    printable_h_cm = printable_h_in * 2.54
    
    max_meters_per_panel = printable_h_cm * scale_meters_per_cm
    
    bh_chunks = [bh_list[i:i + max_boreholes_per_page] for i in range(0, len(bh_list), max_boreholes_per_page)]
    
    with PdfPages(pdf_buffer) as pdf:
        for page_idx, chunk in enumerate(bh_chunks):
            chunk_collars = collar_df[collar_df['BORE ID'].isin(chunk)]
            max_chunk_depth = chunk_collars['DEPTH'].max() if not chunk_collars.empty else 100.0
            
            num_panels = int(np.ceil(max_chunk_depth / max_meters_per_panel))
            if num_panels < 1:
                num_panels = 1
                
            for panel in range(num_panels):
                depth_start = panel * max_meters_per_panel
                depth_end = (panel + 1) * max_meters_per_panel
                panel_depth_range = depth_end - depth_start
                
                panel_h_in = (panel_depth_range / scale_meters_per_cm) / 2.54
                
                fig = plt.figure(figsize=(page_w_in, page_h_in))
                
                page_label = f"Page {page_idx + 1}" + (f" (Panel {panel + 1}/{num_panels})" if num_panels > 1 else "")
                fig.suptitle(
                    f"KL BOREHOLE GRAPHIC LOGS — {page_label}\n"
                    f"Scale: {scale_option} | Column Width: {col_width_cm:.2f} cm | Segment: {depth_start:.1f} m to {depth_end:.1f} m",
                    fontsize=12, fontweight='bold', y=0.96
                )
                
                n_cols = len(chunk)
                slot_w_in = page_w_in / n_cols
                
                for idx, bore_id in enumerate(chunk):
                    c_info = collar_df[collar_df['BORE ID'] == bore_id]
                    if c_info.empty:
                        continue
                    c_info = c_info.iloc[0]
                    
                    closing_depth = float(c_info['DEPTH'])
                    rl = float(c_info['RL'])
                    
                    center_x_in = (idx + 0.5) * slot_w_in
                    left_x_in = center_x_in - (col_width_in / 2.0)
                    bottom_y_in = page_h_in - top_margin_in - header_height_in - panel_h_in
                    
                    norm_rect = [
                        left_x_in / page_w_in,
                        bottom_y_in / page_h_in,
                        col_width_in / page_w_in,
                        panel_h_in / page_h_in
                    ]
                    
                    ax = fig.add_axes(norm_rect)
                    
                    b_litho = litho_df[litho_df['BORE ID'] == bore_id].sort_values('FROM')
                    b_seams = merged_seams_df[merged_seams_df['BORE ID'] == bore_id] if not merged_seams_df.empty else pd.DataFrame()
                    
                    panel_litho = b_litho[(b_litho['TO'] >= depth_start) & (b_litho['FROM'] <= depth_end)]
                    panel_seams = b_seams[(b_seams['TO'] >= depth_start) & (b_seams['FROM'] <= depth_end)] if not b_seams.empty else pd.DataFrame()
                    
                    header_text = (
                        f"BORE ID: {bore_id}\n"
                        f"X: {c_info['X']:.2f} | Y: {c_info['Y']:.2f}\n"
                        f"RL: {rl:.2f} m | Depth: {closing_depth:.2f} m"
                    )
                    ax.text(
                        0.5, 1.02, header_text, transform=ax.transAxes,
                        fontsize=7, fontweight='bold', ha='center', va='bottom',
                        bbox=dict(boxstyle="round,pad=0.3", fc="white", ec="black", lw=0.8)
                    )
                    
                    ax.set_xlim(0, col_width_cm)
                    ax.set_ylim(depth_end, depth_start)
                    
                    for spine in ax.spines.values():
                        spine.set_visible(False)
                        
                    col_bottom = min(closing_depth, depth_end)
                    if closing_depth >= depth_start:
                        ax.plot([0, 0], [max(0.0, depth_start), col_bottom], color='black', lw=1.2, clip_on=False)
                        ax.plot([col_width_cm, col_width_cm], [max(0.0, depth_start), col_bottom], color='black', lw=1.2, clip_on=False)
                        if depth_start == 0:
                            ax.plot([0, col_width_cm], [0, 0], color='black', lw=1.2, clip_on=False)
                        if closing_depth <= depth_end:
                            ax.plot([0, col_width_cm], [closing_depth, closing_depth], color='black', lw=1.2, clip_on=False)
                            
                    for _, row in panel_litho.iterrows():
                        top = float(row['FROM'])
                        bot = float(row['TO'])
                        thick = bot - top
                        lith = str(row['LITHOLOGY']).upper()
                        seam = str(row['SEAM']).upper()
                        
                        if 'COAL' in lith or 'COAL' in seam or (seam != '' and seam != 'NAN'):
                            facecolor = 'black'
                        elif 'SHALE' in lith or 'CARBSHALE' in lith:
                            facecolor = 'dimgray'
                        elif 'SANDSTONE' in lith:
                            facecolor = 'gainsboro'
                        else:
                            facecolor = 'white'
                            
                        ax.add_patch(
                            patches.Rectangle(
                                (0, top), col_width_cm, thick,
                                facecolor=facecolor, edgecolor='black', linewidth=0.25
                            )
                        )
                    
                    major_ticks = np.arange(np.floor(depth_start / 10) * 10, depth_end + 10, 10)
                    minor_ticks = np.arange(np.floor(depth_start / 2) * 2, depth_end + 2, 2)
                    
                    for md in minor_ticks:
                        if depth_start <= md <= min(closing_depth, depth_end) and md not in major_ticks:
                            ax.plot([-0.1, 0], [md, md], color='black', lw=0.5, clip_on=False)
                            
                    for d in major_ticks:
                        if depth_start <= d <= min(closing_depth, depth_end):
                            ax.plot([-0.2, 0], [d, d], color='black', lw=1.0, clip_on=False)
                            ax.text(-0.25, d, f"{int(d)}m", fontsize=7, va='center', ha='right', color='black', fontweight='bold')
                    
                    if not panel_seams.empty:
                        for _, srow in panel_seams.iterrows():
                            s_from = float(srow['FROM'])
                            s_to = float(srow['TO'])
                            s_thick = float(srow['THICKNESS'])
                            s_name = str(srow['SEAM'])
                            s_mid = (s_from + s_to) / 2.0
                            
                            if depth_start <= s_from <= depth_end:
                                ax.plot([-0.15, 0], [s_from, s_from], color='crimson', lw=0.7, clip_on=False)
                                ax.text(-0.18, s_from, f"{s_from:.2f}", fontsize=5.5, va='center', ha='right', color='crimson', fontweight='bold')
                            if depth_start <= s_to <= depth_end:
                                ax.plot([-0.15, 0], [s_to, s_to], color='crimson', lw=0.7, clip_on=False)
                                ax.text(-0.18, s_to, f"{s_to:.2f}", fontsize=5.5, va='center', ha='right', color='crimson', fontweight='bold')
                            
                            b_top = max(s_from, depth_start)
                            b_bot = min(s_to, depth_end)
                            bracket_x = col_width_cm + 0.15
                            
                            ax.plot([col_width_cm, bracket_x], [b_top, b_top], color='black', lw=0.8, clip_on=False)
                            ax.plot([col_width_cm, bracket_x], [b_bot, b_bot], color='black', lw=0.8, clip_on=False)
                            ax.plot([bracket_x, bracket_x], [b_top, b_bot], color='black', lw=0.8, clip_on=False)
                            
                            if depth_start <= s_mid <= depth_end:
                                ax.text(
                                    bracket_x + 0.1, s_mid,
                                    f"{s_name}\n({s_thick:.2f}m)",
                                    fontsize=6.5, fontweight='bold', va='center', ha='left', color='black'
                                )

                    if depth_start <= closing_depth <= depth_end:
                        ax.text(
                            col_width_cm / 2.0, closing_depth + 1.8,
                            f"CD: {closing_depth:.2f} m",
                            fontsize=7, fontweight='bold', ha='center', va='top'
                        )
                    
                    ax.set_xticks([])
                    ax.set_yticks([])
                
                pdf.savefig(fig)
                plt.close(fig)
            
    pdf_buffer.seek(0)
    return pdf_buffer


def create_matplotlib_plan_map(collar_df, boundary_df, selected_bhs):
    """Generate publication-ready Matplotlib map with exact aspect ratio, highlighted targets, and scalebar."""
    fig, ax = plt.subplots(figsize=(10, 8))
    
    if boundary_df is not None:
        b_df = boundary_df.copy()
        b_df.columns = [c.strip().upper() for c in b_df.columns]
        if b_df.iloc[0]['X'] != b_df.iloc[-1]['X'] or b_df.iloc[0]['Y'] != b_df.iloc[-1]['Y']:
            b_df = pd.concat([b_df, b_df.iloc[[0]]], ignore_index=True)
            
        ax.plot(b_df['X'], b_df['Y'], color='darkred', linestyle='--', linewidth=1.8, label='Block Boundary', zorder=2)
        ax.fill(b_df['X'], b_df['Y'], color='red', alpha=0.04, zorder=1)

    c_df = collar_df.copy()
    c_df['SELECTED'] = c_df['BORE ID'].isin(selected_bhs)
    
    unselected_df = c_df[~c_df['SELECTED']]
    selected_df = c_df[c_df['SELECTED']]
    
    norm = plt.Normalize(c_df['DEPTH'].min(), c_df['DEPTH'].max())
    cmap = plt.cm.viridis

    if not unselected_df.empty:
        ax.scatter(
            unselected_df['X'], unselected_df['Y'],
            c=unselected_df['DEPTH'], cmap=cmap, norm=norm,
            s=65, edgecolors='gray', linewidths=0.8, alpha=0.6,
            label='Boreholes', zorder=3
        )

    if not selected_df.empty:
        ax.scatter(
            selected_df['X'], selected_df['Y'],
            s=65, facecolors='none', edgecolors='gold', linewidths=3.0,
            zorder=4, label='Selected Boreholes'
        )
        ax.scatter(
            selected_df['X'], selected_df['Y'],
            c=selected_df['DEPTH'], cmap=cmap, norm=norm,
            s=65, edgecolors='crimson', linewidths=1.5,
            zorder=5
        )

    for _, row in c_df.iterrows():
        is_sel = row['SELECTED']
        ax.annotate(
            row['BORE ID'], (row['X'], row['Y']),
            xytext=(6, 6), textcoords='offset points',
            fontsize=6, fontweight='normal' if not is_sel else 'bold',
            color='black' if not is_sel else 'darkred',
            zorder=6
        )

    ax.set_aspect('equal', adjustable='datalim')
    ax.grid(True, linestyle=':', color='gray', alpha=0.5, zorder=0)

    divider = make_axes_locatable(ax)
    cax = divider.append_axes("right", size="3%", pad=0.15)
    cbar = plt.colorbar(plt.cm.ScalarMappable(norm=norm, cmap=cmap), cax=cax)
    cbar.set_label('Closing Depth (m)', fontsize=10, fontweight='bold')

    x_min, x_max = ax.get_xlim()
    y_min, y_max = ax.get_ylim()
    scale_length_m = 1000 if (x_max - x_min) >= 2000 else 500
    
    sb_x = x_min + (x_max - x_min) * 0.05
    sb_y = y_min + (y_max - y_min) * 0.05
    
    ax.plot([sb_x, sb_x + scale_length_m], [sb_y, sb_y], color='black', lw=3.0, zorder=10)
    ax.text(
        sb_x + scale_length_m / 2.0, sb_y + (y_max - y_min) * 0.015,
        f"{scale_length_m} m", ha='center', va='bottom', fontweight='bold', fontsize=9, zorder=10
    )

    ax.annotate(
        '▲\nN', xy=(0.03, 0.92), xycoords='axes fraction',
        fontsize=10, fontweight='bold', ha='center', va='center',
    )

    ax.set_title("BOREHOLE LOCATION MAP", fontsize=9, pad=5)
    ax.set_xlabel("Easting (X)", fontsize=10, fontweight='bold')
    ax.set_ylabel("Northing (Y)", fontsize=10, fontweight='bold')
    ax.legend(loc='lower right', frameon=True, facecolor='white', edgecolor='black', framealpha=0.9, fontsize=8.5)

    plt.tight_layout()
    return fig


# --- STREAMLIT TABS UI ---
tab1, tab2, tab3, tab4 = st.tabs([
    "📁 Upload Geological Data",
    "📄 Graphic Logs PDF & Settings",
    "🗺️ Plan Map",
    "📋 Merged Seam Data"
])

collar_df, litho_df, boundary_df, merged_seams_df = None, None, None, None

# --- TAB 1: FILE UPLOADS ONLY ---
with tab1:
    st.header("Upload CSV Files")
    col_u1, col_u2, col_u3 = st.columns(3)
    with col_u1:
        collar_file = st.file_uploader("Collar CSV (COLLAR.csv)", type=["csv"])
    with col_u2:
        litho_file = st.file_uploader("Lithology CSV (LITHOLOGY.csv)", type=["csv"])
    with col_u3:
        boundary_file = st.file_uploader("Boundary CSV (BOUNDARY.csv)", type=["csv"])

    if collar_file and litho_file:
        collar_df = pd.read_csv(collar_file)
        litho_df = pd.read_csv(litho_file)
        boundary_df = pd.read_csv(boundary_file) if boundary_file else None
        
        collar_df.columns = [c.strip().upper() for c in collar_df.columns]
        litho_df.columns = [c.strip().upper() for c in litho_df.columns]
        
        merged_seams_df = preprocess_litho(litho_df, max_gap_meters=2.0)
        st.success("✅ CSV files loaded and preprocessed! Switch to Tab 2 ('📄 Graphic Logs PDF & Settings') to configure layout and export.")
    else:
        st.info("👈 Upload `COLLAR.csv` and `LITHOLOGY.csv` here to begin.")

# --- TAB 2: CONFIGURATION, SELECTION & GENERATION ---
with tab2:
    if collar_file and litho_file and collar_df is not None:
        st.header("Layout & Scale Configuration")
        col_c1, col_c2, col_c3, col_c4 = st.columns(4)
        
        with col_c1:
            page_size = st.selectbox("Page Size", options=["A3", "A4", "A2"], index=0)
        with col_c2:
            page_orientation = st.selectbox("Page Orientation", options=["Landscape", "Portrait"], index=0)
        with col_c3:
            scale_option = st.selectbox(
                "Vertical Scale (1 cm = X m)",
                options=["1 cm = 5 m", "1 cm = 10 m", "1 cm = 15 m", "1 cm = 20 m"],
                index=1
            )
            scale_meters_per_cm = float(scale_option.split("=")[1].replace("m", "").strip())
        with col_c4:
            col_width_cm = st.number_input("Log Column Width (cm)", min_value=0.2, max_value=2.0, value=0.5, step=0.1)

        st.markdown("---")
        st.header("Select Boreholes (Max - 5 once)")
        available_bhs = collar_df['BORE ID'].unique().tolist()
        
        selected_bhs = st.multiselect(
            "Choose up to 5 Boreholes for Graphic Logging:",
            options=available_bhs,
            default=available_bhs[:5],
            max_selections=5  # Strict limit constraint
        )
        
        st.markdown(" ")
        generate_btn = st.button("🚀 Generate Graphic Logs PDF", type="primary", use_container_width=True)
        
        if generate_btn:
            if selected_bhs:
                pdf_bytes = create_graphic_logs_pdf(
                    collar_df, litho_df, merged_seams_df, selected_bhs,
                    page_size, page_orientation, scale_option, scale_meters_per_cm, col_width_cm, max_boreholes_per_page=5
                )
                
                # Dynamic PDF File Naming
                if len(selected_bhs) == 1:
                    filename = f"Graphic_Log_{selected_bhs[0]}_{page_size}_{page_orientation}.pdf"
                elif len(selected_bhs) <= 3:
                    bhs_str = "_".join(selected_bhs)
                    filename = f"Graphic_Logs_{bhs_str}_{page_size}_{page_orientation}.pdf"
                else:
                    filename = f"Graphic_Logs_{selected_bhs[0]}_to_{selected_bhs[-1]}_{page_size}_{page_orientation}.pdf"
                
                # Store PDF in session state
                st.session_state.generated_pdf = pdf_bytes
                st.session_state.pdf_filename = filename
                
                st.success("🎉 Graphic logs PDF generated successfully!")
            else:
                st.error("Please select at least 1 borehole.")
        
        st.markdown("---")
        if st.session_state.generated_pdf:
            st.success(f"File Ready: **{st.session_state.pdf_filename}**")
            st.download_button(
                label=f"📥 Download PDF ({st.session_state.pdf_filename})",
                data=st.session_state.generated_pdf,
                file_name=st.session_state.pdf_filename,
                mime="application/pdf",
                type="primary"
            )
    else:
        st.warning("Please upload `COLLAR.csv` and `LITHOLOGY.csv` in Tab 1 first.")

# --- TAB 3: PLAN MAP ---
with tab3:
    st.header("🗺️ BH Location Plan ")
    if collar_df is not None:
        target_bhs = selected_bhs if ('selected_bhs' in locals() and selected_bhs) else collar_df['BORE ID'].unique().tolist()[:5]
        map_fig = create_matplotlib_plan_map(collar_df, boundary_df, target_bhs)
        st.pyplot(map_fig)
    else:
        st.info("Upload collar CSV in Tab 1 to view the Plan Map.")

# --- TAB 4: MERGED SEAMS SUMMARY ---
with tab4:
    st.header("📋 Processed Summary")
    if merged_seams_df is not None:
        st.dataframe(merged_seams_df, use_container_width=True)
    else:
        st.info("Upload lithology CSV in Tab 1 to view the processed seam summary.")
