import streamlit as st
import pandas as pd
import time
import os
from supabase import create_client, Client
from dotenv import load_dotenv
from geopy.geocoders import Nominatim # ✅ NEW: For converting addresses to coordinates

# --- 1. CONFIGURATION & SETUP ---
st.set_page_config(page_title="ParkPal", layout="wide")
load_dotenv()

# Initialize Database Connection
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# --- 2. BACKEND FUNCTIONS (The Brains) ---

@st.cache_data(ttl=10) # ✅ CACHING: Remembers data for 10 seconds to stop lag
def fetch_parking_spots():
    """Fetches all spots from the database, cleans them, and filters bad data."""
    try:
        response = supabase.table("parking_spots").select("*").execute()
    except Exception as e:
        st.error("⚠️ Network Error: Could not connect to Supabase.")
        return pd.DataFrame()

    if not response.data:
        return pd.DataFrame()
    
    df = pd.DataFrame(response.data)
    
    # 1. Drop rows with missing lat/lon
    df = df.dropna(subset=['lat', 'lng'])
    
    # 2. Rename 'lng' to 'lon' for Streamlit Map
    df = df.rename(columns={'lng': 'lon'})
    
    # 3. Geofence: Keep only spots inside Bangalore (roughly)
    # This prevents the map from zooming out to the whole world
    df = df[
        (df['lat'] > 12.8) & (df['lat'] < 13.3) & 
        (df['lon'] > 77.4) & (df['lon'] < 77.8)
    ]
    
    return df

def get_lat_lon(address_text):
    """Converts a text address (e.g., 'Indiranagar') into GPS coordinates."""
    geolocator = Nominatim(user_agent="parkpal_joshua_project")
    try:
        # Append "Bangalore" to be safe
        full_address = f"{address_text}, Bangalore"
        location = geolocator.geocode(full_address)
        if location:
            return location.latitude, location.longitude
        return None, None
    except:
        return None, None

def add_spot(data):
    """Sends a new spot to Supabase."""
    try:
        supabase.table("parking_spots").insert(data).execute()
        return True, "Spot listed successfully!"
    except Exception as e:
        return False, str(e)

def book_spot(spot_id):
    """Updates a spot status to 'Booked'."""
    supabase.table("parking_spots").update({"is_available": False}).eq("id", spot_id).execute()

# --- 3. FRONTEND UI (The Visuals) ---

st.title("🚗 ParkPal: Find a Spot in Bangalore")

# -- SIDEBAR: For Owners --
with st.sidebar:
    st.header("📢 List Your Spot")
    st.write("Enter an address to auto-find coordinates.")
    
    with st.form("listing_form"):
        owner = st.text_input("Your Name")
        
        # ✅ SMART ADDRESS INPUT
        addr_input = st.text_input("Address (Type & Press Enter)", key="addr_input")
        
        # Logic to set default values based on address search
        default_lat, default_lon = 12.9716, 77.5946 # Default: MG Road
        
        if addr_input:
            found_lat, found_lon = get_lat_lon(addr_input)
            if found_lat:
                default_lat, default_lon = found_lat, found_lon
                st.success("📍 Location found! Coordinates updated.")
            else:
                st.warning("Could not find address. Please adjust manually below.")

        # ✅ PRE-FILLED COORDINATE BOXES (Editable)
        lat = st.number_input("Latitude", value=default_lat, format="%.4f")
        lon = st.number_input("Longitude", value=default_lon, format="%.4f")
        
        price = st.number_input("Price (₹/hr)", value=50)
        
        if st.form_submit_button("List Spot"):
            new_spot = {
                "owner_name": owner, "address": addr_input, "price": price, 
                "lat": lat, "lng": lon, "is_available": True
            }
            success, msg = add_spot(new_spot)
            if success:
                st.success(msg)
                time.sleep(1)
                st.rerun()
            else:
                st.error(msg)

# -- MAIN AREA: For Renters --
df = fetch_parking_spots()

if not df.empty:
    # 1. THE SEARCH BAR
    st.subheader("🔍 Find a Spot")
    search_col, filter_col = st.columns([3, 1])
    
    with search_col:
        search_query = st.text_input("Search Location", placeholder="e.g. Indiranagar, Koramangala...")
        
    with filter_col:
        max_price = st.slider("Max Price (₹)", 10, 500, 100)

    # 2. FILTERING LOGIC
    # Start with available spots only
    filtered_df = df[df['is_available'] == True]
    
    # Filter by Price
    filtered_df = filtered_df[filtered_df['price'] <= max_price]
    
    # Filter by Search Text (Case Insensitive)
    if search_query:
        filtered_df = filtered_df[filtered_df['address'].str.contains(search_query, case=False)]

    # 3. RESULTS & MAP
    st.caption(f"Found {len(filtered_df)} spots matching your criteria.")
    st.map(filtered_df)

    # 4. BOOKING LIST
    st.divider()
    if not filtered_df.empty:
        for index, spot in filtered_df.iterrows():
            c1, c2, c3 = st.columns([3, 1, 1])
            with c1:
                st.write(f"**{spot['address']}**")
                st.caption(f"Owner: {spot['owner_name']}")
            with c2:
                st.write(f"**₹{spot['price']}**/hr")
            with c3:
                # Unique key for every button prevents errors
                if st.button("Book", key=f"btn_{spot['id']}"):
                    book_spot(spot['id'])
                    st.success("✅ Booked!")
                    # Clear cache so the map updates instantly
                    fetch_parking_spots.clear()
                    time.sleep(0.5)
                    st.rerun()
    else:
        st.warning("No spots match your search. Try changing the price or location.")
else:
    st.info("No spots available right now. Be the first to list one!")