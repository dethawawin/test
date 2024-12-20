import streamlit as st
from streamlit_option_menu import option_menu
import pandas as pd
from datetime import datetime, timedelta
from io import BytesIO
import xlsxwriter
import plotly.express as px
 
# Default Page Config
st.set_page_config(page_title="SDT Schedule", layout="wide")

# Initialize session state
if "schedule_table" not in st.session_state:
    st.session_state.schedule_table = None
if "updated_stages" not in st.session_state:
    st.session_state.updated_stages = None
if "warna_aktivitas" not in st.session_state:
    st.session_state.warna_aktivitas = None
if "schedule_figure" not in st.session_state:
    st.session_state.schedule_figure = None
if "is_valid" not in st.session_state:
    st.session_state.is_valid = False
 
# Shift Time Range Logic
def get_shift_range(shift):
    if "A" in shift:
        shift_start = datetime.strptime("07:00:00", "%H:%M:%S")
        shift_end = datetime.strptime("18:59:59", "%H:%M:%S")
    else:  # Shift B
        shift_start = datetime.strptime("19:00:00", "%H:%M:%S")
        shift_end = datetime.strptime("06:59:59", "%H:%M:%S") + timedelta(days=1)
    return shift_start, shift_end
 
# Function to display the header
def display_header():
    st.title("PT XYZ Side Dump Truck Departure Scheduling")
    st.markdown("---")  # Adds a horizontal line for better separation
 
# Clear all inputs and results
def clear_all():
    keys_to_reset = [
        "schedule_table",
        "updated_stages",
        "warna_aktivitas",
        "schedule_figure",
        "is_valid",
        "uploaded_file",       # Key for file uploader
        "tonnage_target",      # Key for tonnage input
        "data_preview",        # Key for uploaded data preview
        "reset"                # Key to force reset file uploader
    ]
    for key in keys_to_reset:
        if key in st.session_state:
            del st.session_state[key]
    st.session_state["reset"] = True  # Force reset file uploader
    st.rerun()
 
# Sidebar and Header
if "reset" not in st.session_state:
    st.session_state["reset"] = False
 
# Function to generate schedule table
def generate_schedule_table(truck_ids, capacities, hauling_target, max_trips_per_truck, updated_stages, shift):
    shift_start, shift_end = get_shift_range(shift)
    schedule_table = []
    total_hauling = 0
    num_trips_per_truck = {truck: 0 for truck in truck_ids}
    trip_index = 0
    base_departure_time = shift_start  # Set start time sesuai shift
    last_trip_end_time = {truck: base_departure_time for truck in truck_ids}
 
    while total_hauling < hauling_target:
        current_truck = truck_ids[trip_index % len(truck_ids)]
        capacity = capacities[truck_ids.index(current_truck)]
 
        if num_trips_per_truck[current_truck] >= max_trips_per_truck:
            trip_index += 1
            continue
 
        if num_trips_per_truck[current_truck] == 0:
            departure_time = base_departure_time + timedelta(minutes=trip_index * 10)
        else:
            departure_time = last_trip_end_time[current_truck] + timedelta(minutes=updated_stages["Break"])
 
        # Stop if departure_time exceeds shift_end
        if departure_time > shift_end:
            break
 
        eta_stockpile = departure_time + timedelta(minutes=updated_stages["Travelling to Stockpile"])
        eta_crusher = eta_stockpile + timedelta(minutes=updated_stages["Hauling"] + updated_stages["Gross-Scaling"])
        eta_workshop = eta_crusher + timedelta(minutes=updated_stages["Dumping"] + updated_stages["Tare-Scaling"] + updated_stages["Travelling to Workshop"])
 
        # Check if entire trip fits within the shift
        if eta_workshop > shift_end:
            break
 
        schedule_table.append({
            "Truck Name": current_truck,
            "Departure Time": departure_time.strftime("%H:%M:%S"),
            "ETA Stockpile": eta_stockpile.strftime("%H:%M:%S"),
            "ETA Crusher": eta_crusher.strftime("%H:%M:%S"),
            "ETA Workshop": eta_workshop.strftime("%H:%M:%S"),
            "Tonnage Plan (ton)": capacity
        })
 
        total_hauling += capacity
        num_trips_per_truck[current_truck] += 1
        last_trip_end_time[current_truck] = eta_workshop
        trip_index += 1
 
        if total_hauling >= hauling_target:
            break
 
    return pd.DataFrame(schedule_table)

def generate_gantt_chart(schedule_table, updated_stages, warna_aktivitas, shift, selected_date):
    shift_start, shift_end = get_shift_range(shift)

    # Tambahkan tanggal ke waktu shift_start dan shift_end
    shift_start = datetime.combine(selected_date, shift_start.time())
    shift_end = datetime.combine(selected_date, shift_end.time())
    gantt_data = []

    # Konversi data tabel jadwal menjadi format yang cocok untuk Plotly
    for _, row in schedule_table.iterrows():
        start_time = datetime.combine(selected_date, datetime.strptime(row["Departure Time"], "%H:%M:%S").time())
        truck_name = row["Truck Name"]
        for stage, duration in updated_stages.items():
            end_time = start_time + timedelta(minutes=duration)
            gantt_data.append({
                "Stage": stage,
                "Start": start_time,
                "End": end_time,
                "Truck": truck_name
            })
            start_time = end_time

    gantt_df = pd.DataFrame(gantt_data)

    # Membuat Gantt Chart menggunakan Plotly
    fig = px.timeline(
        gantt_df,
        x_start="Start",
        x_end="End",
        y="Truck",
        color="Stage",
        title=f"Truck Departure Schedule: {selected_date.strftime('%Y-%m-%d')} | Shift {shift}",
        template="plotly_white",
        color_discrete_map=warna_aktivitas
    )

    # Urutkan TruckID secara descending
    truck_order = sorted(gantt_df["Truck"].unique(), reverse=True)
    fig.update_yaxes(categoryorder="array", categoryarray=truck_order)

    # Mengatur format waktu pada sumbu X dan menampilkan tanggal
    fig.update_xaxes(
        range=[shift_start, shift_end],
        tickformat="%H:%M"
    )

    # Tambahkan layout agar grafik terlihat rapi
    fig.update_layout(
        yaxis_title="Truck Name",
        height=700,
        legend_title="Stages",
        margin=dict(l=10, r=10, t=50, b=50)
    )
    return fig
 
# Sidebar menu
with st.sidebar:
    selected_page = option_menu(
        menu_title="Menu",
        options=["Homepage", "Create a New Schedule"],
        icons=["house-door-fill", "calendar-plus-fill"],
        menu_icon='list',
        default_index=0
    )
 
if selected_page == "Homepage":
    display_header()
    st.subheader('About Application')
    st.markdown('The Side Dump Truck departure scheduling system application is designed to efficiently organize and monitor truck departure schedules for coal hauling activities.')
    st.subheader('User Guidance')
    st.markdown("""
    #### Steps to Use the Application:
    1. Navigate to the application and click on the Create Schedule menu.
    2. Enter the required date and shift for the new schedule in the provided fields.
    3. Upload the Ready for Use (RFU) Side Dump Truck data file in .xlsx format with the necessary columns: truckID and capacity.
    4. Input the planned hauling tonnage target into the designated field.
    5. The system validates the tonnage target against available truck capacity.
    6. Generate and view the departure schedule.
    """)
 
