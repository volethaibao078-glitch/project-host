import streamlit as st
import pandas as pd
import plotly.express as px
import unicodedata
import folium
from folium import plugins
from streamlit_folium import st_folium
import ee
from branca.element import Template, MacroElement
import numpy as np

# ==========================================
# 0. CẤU HÌNH TRANG WEB & CSS FULL SCREEN
# ==========================================
st.set_page_config(page_title="WebGIS Diện Tích Nước", layout="wide", initial_sidebar_state="collapsed")

UI_HEIGHT = 800

st.markdown("""
    <style>
        .stApp { overflow: hidden !important; }
        .block-container {
            padding-top: 1rem !important;
            padding-bottom: 0rem !important;
            padding-left: 1rem !important;
            padding-right: 1rem !important;
            max-width: 100% !important;
        }
        header {visibility: hidden;}
        footer {visibility: hidden;}
        
        ::-webkit-scrollbar { width: 5px; height: 5px; }
        ::-webkit-scrollbar-thumb { background: #b0b0b0; border-radius: 10px; }
        ::-webkit-scrollbar-thumb:hover { background: #888; }
    </style>
""", unsafe_allow_html=True)

# ==========================================
# 1. KHỞI TẠO GEE (ĐÃ TỐI ƯU BẰNG CACHE)
# ==========================================
@st.cache_resource
def init_gee():
    try:
        ee.Initialize()
    except Exception as e:
        pass

# Gọi hàm khởi tạo
init_gee()

def add_ee_layer(self, ee_image_object, vis_params, name, opacity=0.6, show=False):
    try:
        map_id_dict = ee.Image(ee_image_object).getMapId(vis_params)
        folium.raster_layers.TileLayer(
            tiles=map_id_dict['tile_fetcher'].url_format,
            attr='Map Data &copy; Google Earth Engine',
            name=name, overlay=True, control=True, opacity=opacity, show=show
        ).add_to(self)
    except:
        pass

folium.Map.add_ee_layer = add_ee_layer

# --- CÁC HÀM LẤY LAYER TỪ GEE ---
@st.cache_data(ttl=3600)
def get_gee_water_url():
    try:
        dataset = ee.Image('JRC/GSW1_4/GlobalSurfaceWater')
        water_layer = dataset.select('occurrence')
        vis_params = {'min': 0, 'max': 100, 'palette': ['ffffff', '0000ff']}
        return ee.Image(water_layer).getMapId(vis_params)['tile_fetcher'].url_format
    except:
        return None

@st.cache_data(ttl=3600)
def get_ndwi_url(year, month):
    try:
        start_date = f'{int(year)}-{int(month):02d}-01'
        end_date = f'{int(year)}-{int(month):02d}-28'
        collection = ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")\
            .filterDate(start_date, end_date)\
            .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 20))
        image = collection.median()
        ndwi = image.normalizedDifference(['B3', 'B8']).rename('NDWI')
        water_mask = ndwi.updateMask(ndwi.gte(0)) 
        vis_params = {'min': 0, 'max': 1, 'palette': ['00FFFF', '0000FF']}
        return ee.Image(water_mask).getMapId(vis_params)['tile_fetcher'].url_format
    except:
        return None

@st.cache_data(ttl=3600)
def get_water_balance_url(year, month):
    try:
        start_date = f'{int(year)}-{int(month):02d}-01'
        end_date = f'{int(year)}-{int(month):02d}-28'
        precip = ee.ImageCollection("UCSB-CHG/CHIRPS/DAILY").filterDate(start_date, end_date).sum()
        et = ee.ImageCollection("MODIS/006/MOD16A2").filterDate(start_date, end_date).select('ET').sum().multiply(0.1)
        balance = precip.subtract(et)
        vis_params = {'min': -50, 'max': 100, 'palette': ['red', 'white', 'blue']}
        return ee.Image(balance).getMapId(vis_params)['tile_fetcher'].url_format
    except:
        return None

@st.cache_data(ttl=3600)
def get_drought_url(year, month):
    try:
        start_date = f'{int(year)}-{int(month):02d}-01'
        end_date = f'{int(year)}-{int(month):02d}-28'
        dataset = ee.ImageCollection('IDAHO_EPSCOR/TERRACLIMATE').filterDate(start_date, end_date)
        pdsi = dataset.select('pdsi').mean()
        vis_params = {'min': -400, 'max': 400, 'palette': ['red', 'orange', 'yellow', 'white', 'lightgreen', 'blue']}
        return ee.Image(pdsi).getMapId(vis_params)['tile_fetcher'].url_format
    except:
        return None

@st.cache_data(ttl=3600)
def get_water_quality_gee_url(year, month, wq_type="TSS"):
    try:
        start_date = f'{int(year)}-{int(month):02d}-01'
        end_date = f'{int(year)}-{int(month):02d}-28'
        collection = ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED").filterDate(start_date, end_date).filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 20))
        image = collection.median()
        
        ndwi = image.normalizedDifference(['B3', 'B8'])
        water_mask = ndwi.gte(0)

        if wq_type == "TSS":
            ndti = image.normalizedDifference(['B4', 'B3']).updateMask(water_mask)
            vis_params = {'min': -0.1, 'max': 0.15, 'palette': ['blue', 'cyan', 'yellow', 'orange', 'red', 'brown']}
            return ee.Image(ndti).getMapId(vis_params)['tile_fetcher'].url_format
        else:
            algae = image.normalizedDifference(['B8', 'B4']).updateMask(water_mask)
            vis_params = {'min': -0.2, 'max': 0.3, 'palette': ['darkblue', 'blue', 'cyan', 'green', 'yellow', 'red']}
            return ee.Image(algae).getMapId(vis_params)['tile_fetcher'].url_format
    except:
        return None

# ==========================================
# 2. HÀM HỖ TRỢ & LOAD DỮ LIỆU
# ==========================================
def get_lat_lon(tinh_name):
    toa_do = {
        'an giang': [10.5216, 105.1259], 'ba ria - vung tau': [10.4973, 107.1683], 'bac lieu': [9.2941, 105.7278],
        'bac giang': [21.2731, 106.1946], 'bac kan': [22.1470, 105.8348], 'bac ninh': [21.1861, 106.0763],
        'ben tre': [10.2440, 106.3753], 'binh duong': [11.1661, 106.6268], 'binh dinh': [13.9030, 109.0528],
        'binh phuoc': [11.7517, 106.7133], 'binh thuan': [11.0877, 108.0722], 'ca mau': [9.1769, 105.1500],
        'can tho': [10.0452, 105.7469], 'cao bang': [22.6667, 106.2500], 'da nang': [16.0678, 108.2208],
        'dak lak': [12.6667, 108.0382], 'dak nong': [12.2606, 107.8056], 'dien bien': [21.3864, 103.0177],
        'dong nai': [10.9410, 106.8209], 'dong thap': [10.4578, 105.6267], 'gia lai': [13.9833, 108.0000],
        'ha giang': [22.8233, 104.9839], 'ha nam': [20.5453, 105.9122], 'ha noi': [21.0285, 105.8542],
        'ha tinh': [18.3428, 105.9054], 'hai duong': [20.9400, 106.3326], 'hau giang': [9.7984, 105.4711], 
        'hoa binh': [20.8133, 105.3383], 'hung yen': [20.8525, 106.0506], 'khanh hoa': [12.2388, 109.1967], 
        'kien giang': [9.8540, 105.1066], 'kon tum': [14.3508, 108.0000], 'lai chau': [22.3956, 103.4519], 
        'lam dong': [11.9465, 108.4419], 'lang son': [21.8485, 106.7583], 'lao cai': [22.4856, 103.9707], 
        'long an': [10.5363, 106.4042], 'nam dinh': [20.4200, 106.1683], 'nghe an': [19.3366, 104.8966], 
        'ninh binh': [20.2539, 105.9750], 'ninh thuan': [11.5646, 108.9886], 'phu tho': [21.3114, 105.2152], 
        'phu yen': [13.0883, 109.3242], 'quang binh': [17.4833, 106.6000], 'quang nam': [15.5411, 107.9942], 
        'quang ngai': [15.1205, 108.7923], 'quang ninh': [21.0069, 107.2925], 'quang tri': [16.7461, 107.1893], 
        'soc trang': [9.6033, 105.9731], 'son la': [21.3253, 103.8974], 'tay ninh': [11.3118, 106.0967], 
        'thai binh': [20.4500, 106.3333], 'thai nguyen': [21.5928, 105.8442], 'thanh hoa': [20.0406, 105.3060], 
        'thua thien hue': [16.4637, 107.5905], 'tien giang': [10.4285, 106.2082], 'ho chi minh': [10.8231, 106.6297], 
        'tra vinh': [9.8211, 106.3025], 'tuyen quang': [21.8214, 105.2131], 'vinh long': [10.2452, 105.9702], 
        'vinh phuc': [21.3089, 105.5960], 'yen bai': [21.7229, 104.9113], 'hai phong': [20.8449, 106.6881],
        'ha tay': [20.9100, 105.7300]  
    }
    s = str(tinh_name).lower().strip()
    s = s.replace('đ', 'd') 
    s = ''.join(c for c in unicodedata.normalize('NFD', s) if unicodedata.category(c) != 'Mn')
    
    if 'ho chi minh' in s: return [10.8231, 106.6297]
    if 'ba ria' in s: return [10.4973, 107.1683]
    if 'thua thien' in s: return [16.4637, 107.5905]
    if 'hai phong' in s: return [20.8449, 106.6881]
    if 'da nang' in s: return [16.0678, 108.2208]
    if 'can tho' in s: return [10.0452, 105.7469]
    if 'ha noi' in s: return [21.0285, 105.8542]
    if 'ha tay' in s: return [20.9100, 105.7300]
    
    return toa_do.get(s, [16.0, 106.0]) 

@st.cache_data 
def load_data():
    try:
        df_all = pd.read_csv('BaoCao_ToanQuoc_2020_2024.csv')
        cols = ['Thang', 'Nam', 'Tinh', 'Dien_Tich_Nuoc_km2', 'NDTI_DoDuc', 'Algae_Tao']
        df_all = df_all[cols]
        df_all['Tinh'] = df_all['Tinh'].astype(str).str.strip()
        df_all = df_all.dropna(subset=['Thang', 'Nam'])
        df_all['Thang'] = df_all['Thang'].astype(int)
        df_all['Nam'] = df_all['Nam'].astype(int)
        df_all['Date'] = pd.to_datetime(df_all['Nam'].astype(str) + '-' + df_all['Thang'].astype(str).str.zfill(2) + '-01')
        return df_all
    except Exception as e:
        st.error(f"Lỗi đọc file dữ liệu cục bộ: {e}")
        return pd.DataFrame()

df = load_data()

# ==========================================
# 3. BỐ CỤC 3 CỘT 
# ==========================================
col_left, col_map, col_right = st.columns([1.8, 6.4, 1.8], gap="small")

# ----------------- CỘT TRÁI (BẢNG ĐIỀU KHIỂN & SO SÁNH) -----------------
with col_left:
    with st.container(height=UI_HEIGHT, border=False):
        st.markdown("### ⚙️ Điều Khiển")
        st.markdown("---")
        
        st.markdown("**1. Khu vực quan tâm**")
        tinh_so_sanh = st.selectbox("Chọn khu vực", ["Toàn Quốc"] + sorted(df['Tinh'].unique().tolist()), key='khuvuc')
        
        st.markdown("<br>**2. Cài đặt thời gian phân tích**", unsafe_allow_html=True)
        c1, c2 = st.columns(2)
        
        all_years = sorted(df['Nam'].unique())
        all_months = sorted(df['Thang'].unique())

        with c1:
            st.write("**Thời điểm 1**")
            nam_1 = st.selectbox("Năm", all_years, key='nam1')
            thang_1 = st.selectbox("Tháng", all_months, key='thang1')
            
        with c2:
            st.write("**Thời điểm 2**")
            valid_years_2 = [y for y in all_years if y >= nam_1]
            nam_2 = st.selectbox("Năm", valid_years_2, key='nam2')
            
            if nam_2 == nam_1:
                valid_months_2 = [m for m in all_months if m > thang_1]
                if not valid_months_2:
                    valid_months_2 = [thang_1] 
            else:
                valid_months_2 = all_months
                
            thang_2 = st.selectbox("Tháng", valid_months_2, key='thang2')

        nam_qk, thang_qk = nam_1, thang_1
        nam_tl, thang_tl = nam_2, thang_2

        start_date = pd.to_datetime(f"{int(nam_qk)}-{int(thang_qk):02d}-01")
        end_date = pd.to_datetime(f"{int(nam_tl)}-{int(thang_tl):02d}-01")

        if start_date == end_date:
            st.warning("⚠️ Thời điểm 2 cần lớn hơn Thời điểm 1 để phân tích biến động hợp lệ.")
        else:
            st.success(f"📌 Đang so sánh:\nTừ: T{int(thang_qk)}/{int(nam_qk)} ➡️ Đến: T{int(thang_tl)}/{int(nam_tl)}")

        st.markdown("<br>**3. Lớp Dữ Liệu & Bản Đồ**", unsafe_allow_html=True)
        layer_type = st.radio("Chọn tính năng hiển thị trực quan:", [
            "1. Biến động diện tích (Chấm tròn tăng/giảm)",
            "2. Cân bằng nước (Marker tỷ lệ % thay đổi)",
            "3. Đánh giá Hạn hán (Cảnh báo đỏ >10%)",
            "4. Mô hình hóa Chất lượng nước (Lấy từ CSV)"
        ])
        
        wq_choice = "TSS"
        if "4. " in layer_type:
            wq_choice = st.selectbox("🔬 Chọn tham số Chất lượng nước:", [
                "Độ đục & TSS (NDTI)", 
                "Tảo nở hoa (Chlorophyll-a)"
            ])

# ----------------- CỘT GIỮA (BẢN ĐỒ FULL TRUNG TÂM) -----------------
with col_map:
    df_qk = df[(df['Nam'] == nam_qk) & (df['Thang'] == thang_qk)].groupby('Tinh').agg({
        'Dien_Tich_Nuoc_km2': 'sum'
    }).reset_index()
    
    df_tl = df[(df['Nam'] == nam_tl) & (df['Thang'] == thang_tl)].groupby('Tinh').agg({
        'Dien_Tich_Nuoc_km2': 'sum',
        'NDTI_DoDuc': 'mean', 
        'Algae_Tao': 'mean'
    }).reset_index()
    
    df_map = pd.merge(df_tl, df_qk, on='Tinh', suffixes=('_tl', '_qk'), how='outer')
    df_map['Dien_Tich_Nuoc_km2_tl'] = df_map['Dien_Tich_Nuoc_km2_tl'].fillna(0)
    df_map['Dien_Tich_Nuoc_km2_qk'] = df_map['Dien_Tich_Nuoc_km2_qk'].fillna(0)
    
    df_map['ChenhLech'] = df_map['Dien_Tich_Nuoc_km2_tl'] - df_map['Dien_Tich_Nuoc_km2_qk']
    df_map['TyLe_PhanTram'] = np.where(df_map['Dien_Tich_Nuoc_km2_qk'] > 0, 
                                      (df_map['ChenhLech'] / df_map['Dien_Tich_Nuoc_km2_qk']) * 100, 0)

    if tinh_so_sanh != "Toàn Quốc":
        df_map = df_map[df_map['Tinh'] == tinh_so_sanh]
        map_center = get_lat_lon(tinh_so_sanh)
        map_zoom = 9 
    else:
        map_center = [16.0, 106.0]
        map_zoom = 5.5

    df_map['Lat'] = df_map['Tinh'].apply(lambda x: get_lat_lon(x)[0])
    df_map['Lon'] = df_map['Tinh'].apply(lambda x: get_lat_lon(x)[1])

    m = folium.Map(location=map_center, zoom_start=map_zoom, control_scale=True, zoom_control=True)

    folium.TileLayer(
        tiles='https://mt1.google.com/vt/lyrs=y&x={x}&y={y}&z={z}',
        attr='Google', name='Google Satellite', overlay=False, control=True
    ).add_to(m)

    minimap = plugins.MiniMap(toggle_display=True, position="bottomright", width=150, height=150)
    m.add_child(minimap)

    # ==========================================
    # LOGIC HIỂN THỊ CÁC TÍNH NĂNG TRÊN BẢN ĐỒ
    # ==========================================
    gee_url = None
    layer_name = 'Layer'
    show_layer = True

    if "1. " in layer_type:
        gee_url = get_gee_water_url()
        layer_name = 'Nước (JRC)'
        show_layer = False 
        
        for idx, row in df_map.iterrows():
            if row['ChenhLech'] > 0:
                color, hien_thi = '#00ff00', f"Tăng: {row['ChenhLech']:.2f} km²"
            elif row['ChenhLech'] < 0:
                color, hien_thi = '#ff0000', f"Giảm: {abs(row['ChenhLech']):.2f} km²"
            else: continue 

            radius = min(2000 + (abs(row['ChenhLech']) * 50), 15000)
            folium.Circle(
                location=[row['Lat'], row['Lon']], radius=radius, color=color, weight=1.5,
                fill=True, fill_color=color, fill_opacity=0.6,
                tooltip=f"<b>{row['Tinh']}</b><br>{hien_thi}"
            ).add_to(m)
            
        legend_html = """
        {% macro html(this, kwargs) %}
        <div style="position: fixed; bottom: 30px; left: 30px; width: 250px; background-color: white; z-index:9999; font-size:14px; border:2px solid grey; border-radius:6px; padding: 10px;">
            <b>Biến động diện tích nước</b><br>
            <i style="background:#00ff00; width: 15px; height: 15px; float: left; margin-right: 8px; border: 1px solid black; border-radius: 50%;"></i> Diện tích nước <b>Tăng</b><br>
            <i style="background:#ff0000; width: 15px; height: 15px; float: left; margin-right: 8px; border: 1px solid black; border-radius: 50%;"></i> Diện tích nước <b>Giảm</b>
        </div>
        {% endmacro %}
        """
        macro = MacroElement()
        macro._template = Template(legend_html)
        m.get_root().add_child(macro)

    elif "2. " in layer_type:
        gee_url = get_water_balance_url(nam_tl, thang_tl)
        layer_name = 'Cân bằng nước GEE (P - ET)'
        show_layer = False
        
        for idx, row in df_map.iterrows():
            pct = row['TyLe_PhanTram']
            if pct > 0:
                icon_color, icon_type = 'blue', 'arrow-up'
                status = "Dư thừa / Tăng trưởng"
            elif pct < 0:
                icon_color, icon_type = 'orange', 'arrow-down'
                status = "Thâm hụt / Suy giảm"
            else: continue

            folium.Marker(
                location=[row['Lat'], row['Lon']],
                icon=folium.Icon(color=icon_color, icon=icon_type, prefix='fa'),
                tooltip=f"<b>{row['Tinh']}</b><br>Trạng thái: {status}<br>Tỷ lệ: {pct:.1f}% so với kỳ trước"
            ).add_to(m)
            
        legend_html = """
        {% macro html(this, kwargs) %}
        <div style="position: fixed; bottom: 30px; left: 30px; width: 260px; background-color: white; z-index:9999; font-size:14px; border:2px solid grey; border-radius:6px; padding: 10px;">
            <b>Cân bằng nước</b><br>
            <i style="background:blue; width: 15px; height: 15px; float: left; margin-right: 8px; border: 1px solid black; border-radius: 50%;"></i> Dư thừa / Tăng trưởng<br>
            <i style="background:orange; width: 15px; height: 15px; float: left; margin-right: 8px; border: 1px solid black; border-radius: 50%;"></i> Thâm hụt / Suy giảm
        </div>
        {% endmacro %}
        """
        macro = MacroElement()
        macro._template = Template(legend_html)
        m.get_root().add_child(macro)

    elif "3. " in layer_type:
        gee_url = get_drought_url(nam_tl, thang_tl)
        layer_name = 'Hạn hán GEE (PDSI)'
        show_layer = True
        
        for idx, row in df_map.iterrows():
            pct = row['TyLe_PhanTram']
            if pct <= -10:
                folium.Marker(
                    location=[row['Lat'], row['Lon']],
                    icon=folium.Icon(color='red', icon='fire', prefix='fa'),
                    tooltip=f"<div style='color:red;'><b>🚨 CẢNH BÁO: {row['Tinh']}</b><br>Diện tích nước sụt giảm mạnh: {pct:.1f}%<br>Nguy cơ khô hạn cao!</div>"
                ).add_to(m)
                
        legend_html = """
        {% macro html(this, kwargs) %}
        <div style="position: fixed; bottom: 30px; left: 30px; width: 280px; background-color: white; z-index:9999; font-size:14px; border:2px solid grey; border-radius:6px; padding: 10px;">
            <b>Đánh giá Hạn hán</b><br>
            <i style="background:red; width: 15px; height: 15px; float: left; margin-right: 8px; border: 1px solid black; border-radius: 50%;"></i> <b>Báo động:</b> Nước sụt giảm > 10%
        </div>
        {% endmacro %}
        """
        macro = MacroElement()
        macro._template = Template(legend_html)
        m.get_root().add_child(macro)

    elif "4. " in layer_type:
        wq_type_code = "TSS" if "TSS" in wq_choice else "CHL"
        gee_url = get_water_quality_gee_url(nam_tl, thang_tl, wq_type_code)
        layer_name = 'Độ đục (NDTI)' if wq_type_code == "TSS" else 'Mức độ Tảo (Chlorophyll-a)'
        
        for idx, row in df_map.iterrows():
            tinh = row['Tinh']
            if wq_type_code == "TSS":
                val = row['NDTI_DoDuc']
                if pd.notna(val) and val != 0:
                    info_text = f"Chỉ số Độ đục (NDTI): <b>{val:.3f}</b>"
                else:
                    info_text = "Không có dữ liệu mặt nước (NDTI = 0) ☁️"
            else:
                val = row['Algae_Tao']
                if pd.notna(val) and val != 0:
                    info_text = f"Chỉ số Tảo: <b>{val:.3f}</b>"
                else:
                    info_text = "Không có dữ liệu mặt nước (Algae = 0) ☁️"

            folium.Marker(
                location=[row['Lat'], row['Lon']],
                icon=folium.Icon(color='cadetblue', icon='info-sign'),
                tooltip=f"<b>{tinh}</b><br>{info_text}"
            ).add_to(m)
            
        if wq_type_code == "TSS":
            legend_html = """
            {% macro html(this, kwargs) %}
            <div style="position: fixed; bottom: 30px; left: 30px; width: 280px; background-color: white; z-index:9999; font-size:14px; border:2px solid grey; border-radius:6px; padding: 10px;">
                <b>Độ đục nước (NDTI)</b><br>
                <i style="background:blue; width: 15px; height: 15px; float: left; margin-right: 8px;"></i> Rất trong <b>(< -0.05)</b><br>
                <i style="background:cyan; width: 15px; height: 15px; float: left; margin-right: 8px;"></i> Trong <b>(-0.05 đến 0)</b><br>
                <i style="background:yellow; width: 15px; height: 15px; float: left; margin-right: 8px;"></i> Hơi đục <b>(0 đến 0.05)</b><br>
                <i style="background:orange; width: 15px; height: 15px; float: left; margin-right: 8px;"></i> Đục <b>(0.05 đến 0.1)</b><br>
                <i style="background:red; width: 15px; height: 15px; float: left; margin-right: 8px;"></i> Rất đục <b>(0.1 đến 0.15)</b><br>
                <i style="background:brown; width: 15px; height: 15px; float: left; margin-right: 8px;"></i> Ô nhiễm <b>(> 0.15)</b>
            </div>
            {% endmacro %}
            """
        else:
            legend_html = """
            {% macro html(this, kwargs) %}
            <div style="position: fixed; bottom: 30px; left: 30px; width: 310px; background-color: white; z-index:9999; font-size:14px; border:2px solid grey; border-radius:6px; padding: 10px;">
                <b>Mức độ Tảo (Chlorophyll-a)</b><br>
                <i style="background:darkblue; width: 15px; height: 15px; float: left; margin-right: 8px;"></i> Rất thấp <b>(< -0.1)</b><br>
                <i style="background:blue; width: 15px; height: 15px; float: left; margin-right: 8px;"></i> Bình thường <b>(-0.1 đến 0)</b><br>
                <i style="background:cyan; width: 15px; height: 15px; float: left; margin-right: 8px;"></i> Có rêu tảo <b>(0 đến 0.1)</b><br>
                <i style="background:green; width: 15px; height: 15px; float: left; margin-right: 8px;"></i> Tảo phát triển <b>(0.1 đến 0.2)</b><br>
                <i style="background:yellow; width: 15px; height: 15px; float: left; margin-right: 8px;"></i> Bùng phát <b>(0.2 đến 0.3)</b><br>
                <i style="background:red; width: 15px; height: 15px; float: left; margin-right: 8px;"></i> Bùng phát nghiêm trọng <b>(> 0.3)</b>
            </div>
            {% endmacro %}
            """
        macro = MacroElement()
        macro._template = Template(legend_html)
        m.get_root().add_child(macro)

    if gee_url:
        folium.raster_layers.TileLayer(
            tiles=gee_url, attr='Map Data &copy; Google Earth Engine',
            name=layer_name, overlay=True, control=True, opacity=0.7, show=show_layer 
        ).add_to(m)

    folium.LayerControl().add_to(m)

    st_folium(m, use_container_width=True, height=UI_HEIGHT, returned_objects=[])

# ----------------- CỘT PHẢI (THỐNG KÊ & BIỂU ĐỒ) -----------------
with col_right:
    # SỬ DỤNG @st.fragment ĐỂ KHI ĐỔI BIỂU ĐỒ BẢN ĐỒ KHÔNG BỊ LOAD LẠI
    @st.fragment
    def render_right_panel():
        with st.container(height=UI_HEIGHT, border=False):
            st.markdown("### 📊 Thống Kê Database")
            st.caption("Trình xuất biểu đồ phân tích dữ liệu toàn quốc.")
            st.markdown("---")
            
            tinh_chart = st.selectbox("Chọn Tỉnh vẽ biểu đồ", sorted(df['Tinh'].unique()))
            
            chu_de_chart = st.selectbox("Chọn Chủ đề biểu đồ:", [
                "1. Biến động diện tích",
                "2. Cân bằng nước",
                "3. Đánh giá Hạn hán",
                "4. Mô hình hóa Chất lượng nước"
            ])
            
            loai_chart = st.selectbox("Chọn Loại biểu đồ:", ["Cột (Bar)", "Đường (Line)", "Tròn (Pie)"])
            
            df_prov = df[df['Tinh'] == tinh_chart].sort_values(by='Date').copy()
            df_prov['ChenhLech_km2'] = df_prov['Dien_Tich_Nuoc_km2'].diff()
            df_prov['TyLe_PhanTram'] = df_prov['Dien_Tich_Nuoc_km2'].pct_change() * 100
            
            nam_chart = st.selectbox("Chọn Năm:", sorted(df['Nam'].unique(), reverse=True), key='nam_chart')
            df_plot = df_prov[df_prov['Nam'] == nam_chart].copy()
            df_plot['Thang'] = df_plot['Thang'].astype(int)
            df_plot['ThoiGian'] = "Tháng " + df_plot['Thang'].astype(str)
                
            if "1." in chu_de_chart:
                y_col = 'Dien_Tich_Nuoc_km2'
                title = f"Diện tích mặt nước (km²)"
                color_seq = ['#87CEFA']
            elif "2." in chu_de_chart:
                y_col = 'ChenhLech_km2'
                title = f"Cân bằng nước (Biến động km² so với tháng trước)"
                color_seq = ['#32CD32']
            elif "3." in chu_de_chart:
                y_col = 'TyLe_PhanTram'
                title = f"Đánh giá Hạn hán (% Thay đổi so với tháng trước)"
                color_seq = ['#FF4500']
            elif "4." in chu_de_chart:
                y_col = ['NDTI_DoDuc', 'Algae_Tao']
                title = f"Chất lượng Nước (Độ đục NDTI & Tảo Chlorophyll)"
                color_seq = ['#D2691E', '#2E8B57']

            legend_layout = dict(orientation="h", yanchor="top", y=-0.7, xanchor="center", x=0.5)

            if not df_plot.empty:
                if loai_chart == "Tròn (Pie)":
                    if isinstance(y_col, list):
                        st.warning("⚠️ Biểu đồ Tròn không hỗ trợ hiển thị 2 chỉ số Chất lượng nước cùng lúc. Vui lòng chọn Cột hoặc Đường.")
                    elif df_plot[y_col].min() < 0:
                        st.warning(f"⚠️ Dữ liệu của chủ đề '{chu_de_chart[3:]}' chứa giá trị âm, không thể vẽ biểu đồ Tròn. Vui lòng chọn Cột hoặc Đường.")
                    else:
                        fig = px.pie(df_plot, names='ThoiGian', values=y_col, hole=0.3, title=title)
                        fig.update_layout(margin=dict(l=0, r=0, t=40, b=50), height=300)
                        fig.update_traces(textposition='inside', textinfo='percent+label')
                        st.plotly_chart(fig, use_container_width=True)
                        
                elif loai_chart == "Cột (Bar)":
                    if isinstance(y_col, list):
                        fig = px.bar(df_plot, x='ThoiGian', y=y_col, title=title, barmode='group', color_discrete_sequence=color_seq)
                    else:
                        fig = px.bar(df_plot, x='ThoiGian', y=y_col, title=title, color_discrete_sequence=color_seq)
                    fig.update_layout(margin=dict(l=0, r=0, t=40, b=50), height=300, legend=legend_layout, legend_title_text='')
                    st.plotly_chart(fig, use_container_width=True)
                    
                elif loai_chart == "Đường (Line)":
                    fig = px.line(df_plot, x='ThoiGian', y=y_col, markers=True, title=title, color_discrete_sequence=color_seq)
                    fig.update_layout(margin=dict(l=0, r=0, t=40, b=50), height=300, legend=legend_layout, legend_title_text='')
                    st.plotly_chart(fig, use_container_width=True)
            else:
                st.warning("Không có dữ liệu để vẽ biểu đồ.")
                
    # Chạy hàm đã được bọc fragment
    render_right_panel()
