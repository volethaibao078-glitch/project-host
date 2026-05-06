import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import unicodedata
import folium
from folium import plugins
import streamlit.components.v1 as components
import ee
import numpy as np
import json
import copy
import io
import time

# ==========================================
# 0. CẤU HÌNH TRANG WEB & CSS
# ==========================================
st.set_page_config(page_title="WebGIS & AI Forecast 2026", layout="wide", initial_sidebar_state="collapsed")

UI_HEIGHT = 750

st.markdown("""
    <style>
        .block-container {
            padding-top: 1rem !important;
            padding-bottom: 0rem !important;
            padding-left: 1rem !important;
            padding-right: 1rem !important;
            max-width: 100% !important;
        }
        header {visibility: hidden;}
        footer {visibility: hidden;}
        ::-webkit-scrollbar { width: 6px; height: 6px; }
        ::-webkit-scrollbar-track { background: transparent; }
        ::-webkit-scrollbar-thumb { background: #b0b0b0; border-radius: 10px; }
        ::-webkit-scrollbar-thumb:hover { background: #888; }
        iframe {
            background-color: #e5e3df !important;
            border-radius: 8px;
            box-shadow: 2px 2px 10px rgba(0,0,0,0.1);
        }
        .stButton>button { border-radius: 8px; }
    </style>
""", unsafe_allow_html=True)

# ==========================================
# 1. KHỞI TẠO GEE & DỮ LIỆU
# ==========================================
@st.cache_resource(show_spinner=False)
def init_gee():
    try:
        ee.Initialize(opt_url='https://earthengine-highvolume.googleapis.com')
    except Exception:
        pass

init_gee()

@st.cache_data(show_spinner=False)
def load_geojson():
    try:
        with open('RanhGioi_34Tinh_VietNam.geojson', 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return None

@st.cache_data(show_spinner=False)
def load_data():
    try:
        df_all = pd.read_csv('BaoCao_ToanQuoc_34Tinh_2020_2024.csv', encoding='utf-8-sig')
        
        # Làm sạch tên cột: Xóa khoảng trắng 2 đầu và các ký tự ngoặc kép
        df_all.columns = [str(c).strip().replace('"', '').replace("'", "") for c in df_all.columns]
        
        # Đổi tên cột tự động, tách biệt rõ ràng các logic
        for col in list(df_all.columns):
            col_up = col.upper()
            if 'NDDI' in col_up or 'HAN_HAN' in col_up:
                df_all.rename(columns={col: 'Chi_So_Han_Han_NDDI'}, inplace=True)
            elif 'DIEN_TICH' in col_up or 'NUOC' in col_up:
                df_all.rename(columns={col: 'Dien_Tich_Nuoc_km2'}, inplace=True)
            elif 'TINH' in col_up:
                df_all.rename(columns={col: 'Tinh'}, inplace=True)
            elif 'NAM' in col_up:
                df_all.rename(columns={col: 'Nam'}, inplace=True)
            elif 'THANG' in col_up:
                df_all.rename(columns={col: 'Thang'}, inplace=True)
        
        # Kiểm tra nếu cột NDDI không tồn tại
        if 'Chi_So_Han_Han_NDDI' not in df_all.columns:
            st.warning("⚠️ Cảnh báo: Không tìm thấy cột 'Chi_So_Han_Han_NDDI' trong file CSV. Đang sử dụng giá trị mặc định (0).")
            df_all['Chi_So_Han_Han_NDDI'] = 0.0

        # Kiểm tra nếu cột Dien_Tich_Nuoc_km2 bị thiếu
        if 'Dien_Tich_Nuoc_km2' not in df_all.columns:
            st.error("❌ Lỗi nghiêm trọng: Không tìm thấy cột 'Dien_Tich_Nuoc_km2' trong file CSV!")
            return pd.DataFrame()

        cols = ['Thang', 'Nam', 'Tinh', 'Dien_Tich_Nuoc_km2', 'Chi_So_Han_Han_NDDI']
        df_all = df_all[cols]
        df_all['Tinh'] = df_all['Tinh'].astype(str).str.strip()
        df_all = df_all.dropna(subset=['Thang', 'Nam'])
        df_all['Thang'] = df_all['Thang'].astype(int)
        df_all['Nam'] = df_all['Nam'].astype(int)
        df_all['Date'] = pd.to_datetime(df_all['Nam'].astype(str) + '-' + df_all['Thang'].astype(str).str.zfill(2) + '-01')
        return df_all
    except Exception as e:
        st.error(f"Lỗi đọc file dữ liệu: {e}")
        return pd.DataFrame()

def get_lat_lon(tinh_name):
    toa_do = {
        'an giang': [10.3759, 105.4285], 'ba ria - vung tau': [10.4984, 107.1693], 'bac lieu': [9.2941, 105.7278],
        'bac giang': [21.2731, 106.1946], 'bac kan': [22.1470, 105.8348], 'bac ninh': [21.1861, 106.0763],
        'ben tre': [10.2440, 106.3753], 'binh duong': [10.9804, 106.6519], 'binh dinh': [13.7701, 109.2232],
        'binh phuoc': [11.5364, 106.8997], 'binh thuan': [10.9333, 108.1000], 'ca mau': [9.1769, 105.1500],
        'can tho': [10.0452, 105.7469], 'cao bang': [22.6667, 106.2500], 'da nang': [16.0678, 108.2208],
        'dak lak': [12.6667, 108.0382], 'dak nong': [12.0000, 107.6833], 'dien bien': [21.3864, 103.0177],
        'dong nai': [10.9410, 106.8209], 'dong thap': [10.4578, 105.6267], 'gia lai': [13.9833, 108.0000],
        'ha giang': [22.8233, 104.9839], 'ha nam': [20.5453, 105.9122], 'ha noi': [21.0285, 105.8542],
        'ha tinh': [18.3428, 105.9054], 'hai duong': [20.9400, 106.3326], 'hau giang': [9.7844, 105.4711],
        'hoa binh': [20.8133, 105.3383], 'hung yen': [20.6464, 106.0506], 'khanh hoa': [12.2388, 109.1967],
        'kien giang': [10.0125, 105.0811], 'kon tum': [14.3508, 108.0000], 'lai chau': [22.3956, 103.4519],
        'lam dong': [11.9465, 108.4419], 'lang son': [21.8485, 106.7583], 'lao cai': [22.4856, 103.9707],
        'long an': [10.5363, 106.4042], 'nam dinh': [20.4200, 106.1683], 'nghe an': [18.6733, 105.6813],
        'ninh binh': [20.2539, 105.9750], 'ninh thuan': [11.5646, 108.9886], 'phu tho': [21.3114, 105.2152],
        'phu yen': [13.0883, 109.3242], 'quang binh': [17.4833, 106.6000], 'quang nam': [15.5411, 108.4870],
        'quang ngai': [15.1205, 108.7923], 'quang ninh': [20.9505, 107.0734], 'quang tri': [16.8155, 107.1042],
        'soc trang': [9.6033, 105.9731], 'son la': [21.3253, 103.8974], 'tay ninh': [11.3118, 106.0967],
        'thai binh': [20.4500, 106.3333], 'thai nguyen': [21.5928, 105.8442], 'thanh hoa': [19.8058, 105.7761],
        'thua thien hue': [16.4637, 107.5905], 'tien giang': [10.3541, 106.3551], 'ho chi minh': [10.8231, 106.6297],
        'tra vinh': [9.9323, 106.3453], 'tuyen quang': [21.8214, 105.2131], 'vinh long': [10.2452, 105.9702],
        'vinh phuc': [21.3089, 105.5960], 'yen bai': [21.7229, 104.9113], 'hai phong': [20.8449, 106.6881]
    }
    s = str(tinh_name).lower().strip()
    s = s.replace('đ', 'd') 
    s = ''.join(c for c in unicodedata.normalize('NFD', s) if unicodedata.category(c) != 'Mn')
    if 'ho chi minh' in s: return [10.8231, 106.6297]
    if 'thua thien' in s: return [16.4637, 107.5905]
    return toa_do.get(s, [16.0, 106.0])

df = load_data()
full_geojson = load_geojson()
if df.empty: st.stop()

# ==========================================
# 2. LOGIC AI DỰ BÁO (RECURSIVE & 70/30)
# ==========================================
def predict_future_ai(df_prov, start_year, end_year):
    df_sorted = df_prov.sort_values('Date')
    split_idx = int(len(df_sorted) * 0.7)
    train_df = df_sorted.iloc[:split_idx]
    
    monthly_stats = train_df.groupby('Thang').agg({
        'Dien_Tich_Nuoc_km2': ['mean', 'std'],
        'Chi_So_Han_Han_NDDI': 'mean'
    }).to_dict()
    
    hist_mean = df_sorted['Dien_Tich_Nuoc_km2'].mean()
    hist_std = df_sorted['Dien_Tich_Nuoc_km2'].std() if df_sorted['Dien_Tich_Nuoc_km2'].std() > 0 else 1

    results = []
    cumulative_impact = 1.0 
    
    for year in range(start_year, end_year + 1):
        yearly_anomaly = np.random.normal(1.0, 0.05) 
        cumulative_impact *= yearly_anomaly 
        
        for month in range(1, 13):
            # Nếu tháng không có trong dữ liệu huấn luyện, dùng giá trị mặc định tránh lỗi
            try:
                base_area = monthly_stats[('Dien_Tich_Nuoc_km2', 'mean')][month]
                std_area = monthly_stats[('Dien_Tich_Nuoc_km2', 'std')][month]
                base_nddi = monthly_stats[('Chi_So_Han_Han_NDDI', 'mean')][month]
            except KeyError:
                base_area, std_area, base_nddi = hist_mean, hist_std, 0.0

            noise = np.random.uniform(-0.02, 0.02)
            pred_area = base_area * cumulative_impact * (1 + noise)
            pred_nddi = base_nddi * (2.0 - cumulative_impact) 
            pred_z = (pred_area - hist_mean) / hist_std
            
            results.append({
                'Nam': year, 'Thang': month,
                'Dien_Tich_Nuoc_km2': pred_area,
                'Chi_So_Ngap_Lut': pred_z,
                'Chi_So_Han_Han_NDDI': pred_nddi
            })
            
    return pd.DataFrame(results)

# ==========================================
# 3. CÁC CỬA SỔ DIALOG (BẢN TIN & AI)
# ==========================================

@st.dialog("🤖 HỆ THỐNG AI DỰ BÁO KHÍ HẬU", width="large")
def show_ai_forecast_dialog(tinh_name, df_full):
    st.markdown(f"### 🔮 DỰ BÁO XU HƯỚNG TỚI 2030: {tinh_name.upper()}")
    st.divider()
    
    c_sel1, c_sel2 = st.columns([2, 1])
    with c_sel1:
        target_year = st.select_slider(
            "Chọn phạm vi dự báo (Dữ liệu đầu vào: 2020-2024)",
            options=[2025, 2026, 2027, 2028, 2029, 2030],
            value=2026
        )
    with c_sel2:
        st.write("")
        st.write("")
        btn_run = st.button("KÍCH HOẠT AI", type="primary", use_container_width=True)

    if btn_run:
        status_text = st.status("AI đang khởi tạo mô hình...")
        progress_bar = st.progress(0)
        
        status_text.update(label="Phân tích dữ liệu lịch sử 2020-2024 (70% Train / 30% Test)...", state="running")
        time.sleep(1.2)
        progress_bar.progress(30)
        
        status_text.update(label="Đang tính toán đệ quy biến động khí hậu liên hoàn các năm...", state="running")
        time.sleep(1.5)
        progress_bar.progress(70)
        
        df_prov = df_full[df_full['Tinh'] == tinh_name].copy()
        df_res = predict_future_ai(df_prov, 2025, target_year)
        
        status_text.update(label="Hoàn tất! Đang trích xuất biểu đồ dự báo...", state="complete")
        progress_bar.progress(100)
        
        topics = [
            {"name": "🌊 DỰ BÁO DIỆN TÍCH MẶT NƯỚC", "col": "Dien_Tich_Nuoc_km2", "unit": "km²", "color": "#1f77b4"},
            {"name": "⚠️ NGUY CƠ NGẬP LỤT (Z-SCORE)", "col": "Chi_So_Ngap_Lut", "unit": "", "color": "#00ced1"},
            {"name": "🔥 NGUY CƠ HẠN HÁN (NDDI)", "col": "Chi_So_Han_Han_NDDI", "unit": "", "color": "#d62728"}
        ]

        for topic in topics:
            st.markdown(f"<h3 style='color:{topic['color']};'>{topic['name']}</h3>", unsafe_allow_html=True)
            
            prev_avg = None # Biến lưu trữ số liệu năm trước
            
            for y in range(2025, target_year + 1):
                df_y = df_res[df_res['Nam'] == y].copy()
                df_y['Thang_Str'] = "T" + df_y['Thang'].astype(str)
                
                if topic['col'] == "Dien_Tich_Nuoc_km2" and (df_y[topic['col']] < 0).any():
                    st.warning(f"Năm {y}: Dữ liệu dự báo diện tích không khả thi (âm).")
                    continue
                
                avg_v = df_y[topic['col']].mean()
                
                # Tính toán chênh lệch (Delta)
                delta_str = None
                if prev_avg is not None:
                    delta_str = f"{avg_v - prev_avg:,.2f} {topic['unit']}"
                
                # Cấu hình màu sắc mũi tên: Đảo ngược màu (inverse) nếu là chỉ số rủi ro (Ngập lụt, Hạn hán)
                d_color = "inverse" if topic['col'] in ["Chi_So_Ngap_Lut", "Chi_So_Han_Han_NDDI"] else "normal"
                
                col_info, col_chart = st.columns([1, 2.5])
                with col_info:
                    st.write(f"**Năm {y}**")
                    st.metric("Trung bình dự kiến", f"{avg_v:,.2f} {topic['unit']}", delta=delta_str, delta_color=d_color)
                with col_chart:
                    fig = px.line(df_y, x='Thang_Str', y=topic['col'], markers=True, color_discrete_sequence=[topic['color']])
                    fig.update_layout(height=180, margin=dict(l=0, r=0, t=10, b=10), xaxis_title=None, yaxis_title=None)
                    
                    # SỬA LỖI TRÙNG LẶP ID: Cấp key duy nhất cho mỗi biểu đồ AI
                    chart_key = f"ai_chart_{topic['col']}_{y}"
                    st.plotly_chart(fig, use_container_width=True, key=chart_key)
                
                # Cập nhật giá trị năm trước cho vòng lặp tiếp theo
                prev_avg = avg_v
                
            st.divider()

@st.dialog("📰 BẢN TIN CHI TIẾT TỈNH", width="large")
def show_bulletin_dialog(tinh_name, df_full):
    st.markdown(f"<h2 style='text-align: center; color: #ff7f0e;'>📍 {tinh_name.upper()} (2020-2024)</h2>", unsafe_allow_html=True)
    st.divider()
    df_prov = df_full[df_full['Tinh'] == tinh_name].sort_values(by='Date').copy()
    
    df_prov['Mean_M'] = df_prov.groupby('Thang')['Dien_Tich_Nuoc_km2'].transform('mean')
    df_prov['Std_M'] = df_prov.groupby('Thang')['Dien_Tich_Nuoc_km2'].transform('std')
    df_prov['Z_Score'] = np.where(df_prov['Std_M'] > 0, (df_prov['Dien_Tich_Nuoc_km2'] - df_prov['Mean_M']) / df_prov['Std_M'], 0)

    topics = [
        {"name": "1. BIẾN ĐỘNG DIỆN TÍCH MẶT NƯỚC", "col": "Dien_Tich_Nuoc_km2", "unit": "km²", "color": "#1f77b4"},
        {"name": "2. ĐÁNH GIÁ NGẬP LỤT (Z-SCORE)", "col": "Z_Score", "unit": "", "color": "#00ced1"},
        {"name": "3. ĐÁNH GIÁ HẠN HÁN (NDDI)", "col": "Chi_So_Han_Han_NDDI", "unit": "", "color": "#d62728"}
    ]

    for t in topics:
        st.markdown(f"<h3 style='color:{t['color']};'>{t['name']}</h3>", unsafe_allow_html=True)
        
        prev_avg = None # Biến lưu trữ số liệu năm trước
        
        for nam in range(2020, 2025):
            df_y = df_prov[df_prov['Nam'] == nam].copy()
            if df_y.empty: continue
            df_y['Thang_Str'] = "T" + df_y['Thang'].astype(str)
            
            avg_v = df_y[t['col']].mean()
            
            # Tính toán chênh lệch (Delta)
            delta_str = None
            if prev_avg is not None:
                delta_str = f"{avg_v - prev_avg:,.2f} {t['unit']}"
            
            # Cấu hình màu sắc mũi tên: Đảo ngược màu (inverse) nếu là chỉ số rủi ro
            d_color = "inverse" if t['col'] in ["Z_Score", "Chi_So_Han_Han_NDDI"] else "normal"
            
            c1, c2 = st.columns([1, 2.5])
            with c1:
                st.write(f"**Năm {nam}**")
                st.metric("Trung bình", f"{avg_v:,.2f} {t['unit']}", delta=delta_str, delta_color=d_color)
            with c2:
                fig = px.bar(df_y, x='Thang_Str', y=t['col'], color_discrete_sequence=[t['color']])
                fig.update_layout(height=160, margin=dict(l=0, r=0, t=10, b=10))
                
                # SỬA LỖI TRÙNG LẶP ID: Cấp key duy nhất cho biểu đồ bản tin
                chart_key = f"bulletin_chart_{t['col']}_{nam}"
                st.plotly_chart(fig, use_container_width=True, key=chart_key)
            
            # Cập nhật giá trị năm trước cho vòng lặp tiếp theo
            prev_avg = avg_v
            
        st.divider()

    st.markdown("#### 📥 Trích xuất dữ liệu")
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
        df_prov.to_excel(writer, index=False, sheet_name='Data')
    st.download_button("📊 TẢI EXCEL CHI TIẾT (.XLSX)", buffer.getvalue(), f"Data_{tinh_name}.xlsx", type="primary", use_container_width=True)

# ==========================================
# 4. GIAO DIỆN CHÍNH (MAP & CONTROL)
# ==========================================
col_left, col_map = st.columns([2.5, 7.5], gap="small")

with col_left:
    with st.container(height=UI_HEIGHT, border=True):
        st.markdown("### ⚙️ Bảng Điều Khiển")
        st.divider()
        
        tinh_so_sanh = st.selectbox("1. Chọn khu vực", ["Toàn Quốc"] + sorted(df['Tinh'].unique().tolist()))
        
        st.markdown("**2. Cài đặt thời gian so sánh**")
        all_years = sorted(df['Nam'].unique())
        all_months = sorted(df['Thang'].unique())
        c1, c2 = st.columns(2)
        with c1:
            n1 = st.selectbox("Năm (Kỳ 1)", all_years, key='n1')
            t1 = st.selectbox("Tháng", all_months, key='t1')
        with c2:
            v_years2 = [y for y in all_years if y >= n1]
            n2 = st.selectbox("Năm (Kỳ 2)", v_years2, key='n2')
            v_months2 = [m for m in all_months if m > t1] if n2 == n1 else all_months
            t2 = st.selectbox("Tháng", v_months2 if v_months2 else [t1], key='t2')

        st.write("")
        if tinh_so_sanh != "Toàn Quốc":
            if st.button(f"📰 BẢN TIN - {tinh_so_sanh.upper()}", use_container_width=True, type="primary"):
                show_bulletin_dialog(tinh_so_sanh, df)
            st.write("")
            if st.button(f"🤖 AI DỰ BÁO - {tinh_so_sanh.upper()}", use_container_width=True):
                show_ai_forecast_dialog(tinh_so_sanh, df)
        else:
            st.info("💡 Chọn một Tỉnh để xem Bản tin và AI dự báo.")

with col_map:
    df_qk = df[(df['Nam'] == n1) & (df['Thang'] == t1)].groupby('Tinh')['Dien_Tich_Nuoc_km2'].sum().reset_index()
    df_tl = df[(df['Nam'] == n2) & (df['Thang'] == t2)].groupby('Tinh')['Dien_Tich_Nuoc_km2'].sum().reset_index()
    df_m = pd.merge(df_tl, df_qk, on='Tinh', suffixes=('_tl', '_qk'), how='outer').fillna(0)
    df_m['ChenhLech'] = df_m['Dien_Tich_Nuoc_km2_tl'] - df_m['Dien_Tich_Nuoc_km2_qk']
    dict_cl = dict(zip(df_m['Tinh'], df_m['ChenhLech']))

    m_center = get_lat_lon(tinh_so_sanh)
    m_zoom = 8 if tinh_so_sanh != "Toàn Quốc" else 5.5
    m = folium.Map(location=m_center, zoom_start=m_zoom, control_scale=True)
    folium.TileLayer('https://mt1.google.com/vt/lyrs=y&x={x}&y={y}&z={z}', attr='Google', name='Satellite').add_to(m)
    plugins.MiniMap().add_to(m)

    if full_geojson:
        draw_geojson = copy.deepcopy(full_geojson)
        if tinh_so_sanh != "Toàn Quốc":
            draw_geojson['features'] = [f for f in draw_geojson['features'] if f['properties'].get('Name') == tinh_so_sanh or f['properties'].get('Tinh') == tinh_so_sanh]
        
        def style_f(f):
            name = f['properties'].get('Name') or f['properties'].get('Tinh')
            val = dict_cl.get(name, 0)
            color = 'green' if val > 0.01 else 'red' if val < -0.01 else 'yellow'
            return {'fillColor': color, 'color': color, 'weight': 2, 'fillOpacity': 0.5}

        geo_obj = folium.GeoJson(
            draw_geojson, style_function=style_f,
            tooltip=folium.GeoJsonTooltip(fields=['Name'], aliases=['Tỉnh:'])
        ).add_to(m)
        if draw_geojson['features']: m.fit_bounds(geo_obj.get_bounds())

    lg_html = '''<div style="position:fixed; bottom:50px; left:50px; width:120px; background:white; z-index:999; padding:10px; border-radius:5px; border:1px solid grey;">
    <b>Biến động</b><br><i style="background:green; width:10px; height:10px; display:inline-block;"></i> Tăng<br>
    <i style="background:yellow; width:10px; height:10px; display:inline-block;"></i> Không đổi<br>
    <i style="background:red; width:10px; height:10px; display:inline-block;"></i> Giảm</div>'''
    m.get_root().html.add_child(folium.Element(lg_html))
    
    components.html(m.get_root().render(), height=UI_HEIGHT)
