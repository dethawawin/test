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

    # Gabungkan shift_start dan shift_end dengan tanggal terpilih
    shift_start = datetime.combine(selected_date, shift_start.time())
    shift_end = datetime.combine(selected_date, shift_end.time())

    # Jika shift_end secara waktu lebih kecil dari shift_start, berarti shift melewati tengah malam
    if shift_end < shift_start:
        shift_end += timedelta(days=1)

    gantt_data = []

    # Konversi data tabel jadwal menjadi format yang cocok untuk Plotly
    for _, row in schedule_table.iterrows():
        departure_str = row["Departure Time"]
        departure_time_obj = datetime.strptime(departure_str, "%H:%M:%S").time()
        start_time = datetime.combine(selected_date, departure_time_obj)

        # Jika Shift B dan start_time < shift_start, berarti waktunya sudah masuk hari berikutnya
        if "B" in shift and start_time < shift_start:
            start_time += timedelta(days=1)

        truck_name = row["Truck Name"]

        # Iterasi setiap stage dan durasinya
        for stage, duration in updated_stages.items():
            end_time = start_time + timedelta(minutes=duration)

            # Cek lagi jika end_time juga perlu disesuaikan dengan hari berikutnya
            if "B" in shift and end_time < shift_start:
                end_time += timedelta(days=1)

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

    # Urutkan TruckID secara descending agar lebih rapi
    truck_order = sorted(gantt_df["Truck"].unique(), reverse=True)
    fig.update_yaxes(categoryorder="array", categoryarray=truck_order)

    # Atur range sumbu X sesuai shift
    fig.update_xaxes(
        range=[shift_start, shift_end],
        tickformat="%H:%M"
    )

    # Layout tambahan
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
    1. Navigate to the application and click the "Create a New Schedule" menu.
    2. Enter the required date and shift for the new schedule in the provided fields.
    3. Upload the Ready for Use (RFU) Side Dump Truck data file in .xlsx format with the necessary columns: truckID and capacity.
    4. Based on the number of SDT RFUs, the system will calculate the hauling capacity. Next, input the planned hauling tonnage target, which must not exceed the hauling capacity that will be notified to the system.
    5. Then, the system validates the tonnage target.
    6. Generate and view the departure schedule.
    """)
 
if selected_page == "Create a New Schedule":
    st.title("Create a New Schedule")
    st.write("Fill in the details below to create a new schedule for the Side Dump Truck.")
    date = st.date_input("Select Operation Date:")
    shift = st.radio("Select Shift:", ["A (07:00:00 - 18:59:59)", "B (19:00:00 - 06:59:59)"])

    uploaded_file = st.file_uploader(
        "Upload RFU File:", type=["xlsx"], key="uploaded_file" if not st.session_state["reset"] else "reset_uploaded_file"
    )
    st.markdown("<i style='font-size: 0.9rem;'>Ensure the file is in Excel format (.xlsx) and includes 'truckID' and 'capacity' columns</i>", unsafe_allow_html=True)

    if uploaded_file:
        try:
            data = pd.read_excel(uploaded_file)
            required_columns = {"truckID", "capacity"}
            if not required_columns.issubset(data.columns):
                st.error(f"Error: Missing required columns {required_columns - set(data.columns)} in the uploaded file.")
                st.session_state.is_valid = False
            else:
                st.write("Uploaded RFU Data Preview:")
                st.dataframe(data.head(5))
                capacities = data['capacity']
                truck_ids = data['truckID'].tolist()
                max_trips_per_truck = 2
                max_capacity = sum(capacities * max_trips_per_truck)

                hauling_target = st.number_input(
                    f"Input Hauling Tonnage Target (maximum {max_capacity:.2f} tons):",
                    min_value=0,
                    max_value=max_capacity,
                    key="tonnage_target"
                )

                if hauling_target > max_capacity:
                    st.error(f"Error: Hauling target exceeds maximum capacity of {max_capacity:.2f} tons.")
                    st.session_state.is_valid = False
                elif hauling_target <= 0:
                    st.error("Error: Hauling target must be greater than 0.")
                    st.session_state.is_valid = False
                else:
                    st.session_state.is_valid = True

                if st.button("Generate Schedule", type="primary") and st.session_state.is_valid:
                    updated_stages = {
                        "Travelling to Stockpile": 68.5,
                        "Loading": 9.2,
                        "Hauling": 141.4,
                        "Gross-Scaling": 3.08,
                        "Dumping": 5.07,
                        "Tare-Scaling": 1.82,
                        "Travelling to Workshop": 42.5,
                        "Break": 30
                    }
                    warna_aktivitas = {
                        "Travelling to Stockpile": "gold",
                        "Loading": "steelblue",
                        "Hauling": "forestgreen",
                        "Gross-Scaling": "blueviolet",
                        "Dumping": "red",
                        "Tare-Scaling": "orange",
                        "Travelling to Workshop": "coral",
                        "Break": "gray"
                    }

                    # Generate schedule table
                    max_trips_per_truck = 2
                    schedule_table = generate_schedule_table(
                        truck_ids=truck_ids,
                        capacities=capacities,
                        hauling_target=hauling_target,
                        max_trips_per_truck=max_trips_per_truck,
                        updated_stages=updated_stages,
                        shift=shift
                    )
                    schedule_table.index = range(1, len(schedule_table) + 1)

                    # Store results in session state
                    st.session_state.schedule_table = schedule_table
                    st.session_state.updated_stages = updated_stages
                    st.session_state.warna_aktivitas = warna_aktivitas

                    st.markdown("---")
                    st.subheader("PT XYZ - Coal Hauling SDT Departure Schedule")
                    #st.dataframe(schedule_table)
                    st.dataframe(schedule_table, use_container_width=True)

                    # Generate and display Gantt chart using Plotly
                    st.subheader("Interactive Gantt Chart")
                    gantt_chart_figure = generate_gantt_chart(
                        schedule_table=schedule_table,
                        updated_stages=updated_stages,
                        warna_aktivitas=warna_aktivitas,
                        shift=shift,
                        selected_date=date
                    )
                    st.plotly_chart(gantt_chart_figure, use_container_width=True)

                    

        except Exception as e:
            st.error(f"Error reading the uploaded file. Please check the file format. Details: {str(e)}")

        if st.session_state.is_valid and st.session_state.schedule_figure is not None:
            st.pyplot(st.session_state.schedule_figure)
           

    # Clear all button
    if st.session_state.schedule_table is not None:
        col1, col2, col3 = st.columns([1, 2, 1])
        with col1:  # Center the button
            if st.button("Clear Schedule"):
                clear_all()
