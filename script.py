import os
import io
import zipfile
import csv
from datetime import datetime, timedelta, timezone
from typing import List, Tuple, Dict
import tempfile
import uuid
from flask import Flask, jsonify, request, send_file
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import Column, Integer, String, DateTime, Float, create_engine
from sqlalchemy.orm import sessionmaker, scoped_session
from sqlalchemy.ext.declarative import declarative_base
import pandas as pd
from concurrent.futures import ThreadPoolExecutor
import pytz

# --- Configuration ---
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# Create Base class for models
Base = db.Model

# --- Database Models ---
class StoreStatus(Base):
    """
    Represents the status of a store at a given timestamp.
    """
    __tablename__ = 'store_status'
    id = Column(Integer, primary_key=True)
    store_id = Column(String(100), nullable=False)
    timestamp_utc = Column(DateTime(timezone=True), nullable=False)
    status = Column(String(20), nullable=False)  # 'active' or 'inactive'

    def __repr__(self):
        return f"<StoreStatus(store_id={self.store_id}, timestamp_utc={self.timestamp_utc}, status={self.status})>"

class BusinessHours(Base):
    """
    Represents the business hours of a store for a specific day of the week.
    """
    __tablename__ = 'business_hours'
    id = Column(Integer, primary_key=True)
    store_id = Column(String(100), nullable=False)
    day_of_week = Column(Integer, nullable=False)  # 0=Monday, 6=Sunday
    start_time_local = Column(String(20), nullable=False)  # HH:MM:SS
    end_time_local = Column(String(20), nullable=False)    # HH:MM:SS

    def __repr__(self):
        return f"<BusinessHours(store_id={self.store_id}, day_of_week={self.day_of_week}, start_time_local={self.start_time_local}, end_time_local={self.end_time_local})>"

class StoreTimezone(Base):
    """
    Represents the timezone of a store.
    """
    __tablename__ = 'store_timezone'
    id = Column(Integer, primary_key=True)
    store_id = Column(String(100), nullable=False)
    timezone_str = Column(String(100), nullable=False)

    def __repr__(self):
        return f"<StoreTimezone(store_id={self.store_id}, timezone_str={self.timezone_str})>"

class Report(Base):
    """
    Represents the status of a generated report.
    """
    __tablename__ = 'reports'
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    status = Column(String(20), default='Running')  # 'Running', 'Complete', 'Error'
    filename = Column(String(255), nullable=True)  # Store the filename of the generated CSV

    def __repr__(self):
        return f"<Report(id={self.id}, status={self.status}, filename={self.filename})>"

# Create engine and session
db_session = db.session

# Initialize report executor
report_executor = ThreadPoolExecutor(max_workers=1)

# --- Helper Functions ---

def parse_time_to_minutes(time_str: str) -> int:
    """Parses a time string (HH:MM:SS) to minutes since midnight."""
    try:
        h, m, s = map(int, time_str.split(':'))
        return h * 60 + m + s // 60
    except ValueError:
        return 0 # Handle invalid time format

def calculate_overlap(
        business_start_minutes: int,
        business_end_minutes: int,
        interval_start_minutes: int,
        interval_end_minutes: int
) -> int:
    """
    Calculates the overlap between business hours and a given time interval in minutes.

    Args:
        business_start_minutes: Business hours start in minutes since midnight.
        business_end_minutes: Business hours end in minutes since midnight.
        interval_start_minutes: Interval start in minutes since midnight.
        interval_end_minutes: Interval end in minutes since midnight.

    Returns:
        The number of overlapping minutes.
    """
    overlap_start = max(business_start_minutes, interval_start_minutes)
    overlap_end = min(business_end_minutes, interval_end_minutes)
    return max(0, overlap_end - overlap_start)

def get_store_timezone(session, store_id: str) -> str:
    """
    Retrieves the timezone string for a given store ID from the database.

    Args:
        session: The database session.
        store_id: The ID of the store.

    Returns:
        The timezone string (e.g., 'America/Chicago').  Defaults to 'America/Chicago' if not found.
    """
    timezone_record = session.query(StoreTimezone).filter_by(store_id=store_id).first()
    return timezone_record.timezone_str if timezone_record else 'America/Chicago'

def get_business_hours(session, store_id: str, day_of_week: int) -> Tuple[int, int]:
    """
    Retrieves the business hours for a given store ID and day of the week from the database.

    Args:
        session: The database session.
        store_id: The ID of the store.
        day_of_week: The day of the week (0=Monday, 6=Sunday).

    Returns:
        A tuple containing the start and end times in minutes since midnight.
        If no business hours are found, returns (0, 24*60).
    """
    business_hours_record = session.query(BusinessHours).filter_by(store_id=store_id, day_of_week=day_of_week).first()
    if business_hours_record:
        start_minutes = parse_time_to_minutes(business_hours_record.start_time_local)
        end_minutes = parse_time_to_minutes(business_hours_record.end_time_local)
        return start_minutes, end_minutes
    else:
        return 0, 24 * 60  # Default to 24/7 if no specific hours are found

def calculate_uptime_downtime(
        session: sessionmaker,
        store_id: str,
        start_time: datetime,
        end_time: datetime
) -> Tuple[int, int]:
    """
    Calculates the uptime and downtime in minutes for a given store within a time range,
    considering business hours.

    Args:
        session: The database session.
        store_id: The ID of the store.
        start_time: The start time of the period (datetime object in UTC).
        end_time: The end time of the period (datetime object in UTC).

    Returns:
        A tuple containing the uptime and downtime in minutes.
    """
    timezone_str = get_store_timezone(session, store_id)
    local_timezone = pytz.timezone(timezone_str)

    # Convert times to store's local timezone
    local_start_time = start_time.replace(tzinfo=timezone.utc).astimezone(local_timezone)
    local_end_time = end_time.replace(tzinfo=timezone.utc).astimezone(local_timezone)

    # Get the latest status before start_time to know the initial state
    initial_status = session.query(StoreStatus).filter(
        StoreStatus.store_id == store_id,
        StoreStatus.timestamp_utc <= start_time
    ).order_by(StoreStatus.timestamp_utc.desc()).first()

    # Fetch store status data within the given time range
    status_records = session.query(StoreStatus).filter(
        StoreStatus.store_id == store_id,
        StoreStatus.timestamp_utc >= start_time,
        StoreStatus.timestamp_utc <= end_time
    ).order_by(StoreStatus.timestamp_utc).all()

    uptime = 0
    downtime = 0

    # If no records at all, consider the entire period as downtime
    if not initial_status and not status_records:
        day_of_week = local_start_time.weekday()
        business_start_minutes, business_end_minutes = get_business_hours(session, store_id, day_of_week)
        
        interval_start_minutes = local_start_time.hour * 60 + local_start_time.minute
        interval_end_minutes = local_end_time.hour * 60 + local_end_time.minute
        
        overlap_minutes = calculate_overlap(
            business_start_minutes,
            business_end_minutes,
            interval_start_minutes,
            interval_end_minutes
        )
        downtime += overlap_minutes
        return uptime, downtime

    current_time = local_start_time
    current_status = initial_status.status if initial_status else 'inactive'

    # Process all status changes within the time range
    all_status_points = []
    
    # Add start time with initial status
    all_status_points.append((local_start_time, current_status))
    
    # Add all status changes
    for record in status_records:
        local_record_time = record.timestamp_utc.replace(tzinfo=timezone.utc).astimezone(local_timezone)
        if local_record_time > local_start_time and local_record_time < local_end_time:
            all_status_points.append((local_record_time, record.status))
    
    # Add end time with last known status
    last_status = status_records[-1].status if status_records else current_status
    all_status_points.append((local_end_time, last_status))

    # Calculate uptime/downtime between each consecutive pair of points
    for i in range(len(all_status_points) - 1):
        current_point = all_status_points[i]
        next_point = all_status_points[i + 1]
        
        current_time = current_point[0]
        next_time = next_point[0]
        current_status = current_point[1]

        # If times are on different days, split the calculation
        if current_time.date() != next_time.date():
            # Handle current day until midnight
            day_end = current_time.replace(hour=23, minute=59, second=59)
            day_of_week = current_time.weekday()
            business_start_minutes, business_end_minutes = get_business_hours(session, store_id, day_of_week)
            
            interval_start_minutes = current_time.hour * 60 + current_time.minute
            interval_end_minutes = 23 * 60 + 59
            
            overlap_minutes = calculate_overlap(
                business_start_minutes,
                business_end_minutes,
                interval_start_minutes,
                interval_end_minutes
            )
            
            if current_status == 'active':
                uptime += overlap_minutes
            else:
                downtime += overlap_minutes

            # Handle next day from midnight until next_time
            day_start = next_time.replace(hour=0, minute=0, second=0)
            day_of_week = next_time.weekday()
            business_start_minutes, business_end_minutes = get_business_hours(session, store_id, day_of_week)
            
            interval_start_minutes = 0
            interval_end_minutes = next_time.hour * 60 + next_time.minute
            
            overlap_minutes = calculate_overlap(
                business_start_minutes,
                business_end_minutes,
                interval_start_minutes,
                interval_end_minutes
            )
            
            if current_status == 'active':
                uptime += overlap_minutes
            else:
                downtime += overlap_minutes
        else:
            # Same day calculation
            day_of_week = current_time.weekday()
            business_start_minutes, business_end_minutes = get_business_hours(session, store_id, day_of_week)
            
            interval_start_minutes = current_time.hour * 60 + current_time.minute
            interval_end_minutes = next_time.hour * 60 + next_time.minute
            
            overlap_minutes = calculate_overlap(
                business_start_minutes,
                business_end_minutes,
                interval_start_minutes,
                interval_end_minutes
            )
            
            if current_status == 'active':
                uptime += overlap_minutes
            else:
                downtime += overlap_minutes

    return uptime, downtime

def generate_store_report(session, store_id: str, now: datetime) -> Dict[str, float]:
    """Generates a report for a single store.

    Args:
        session: The database session.
        store_id: The ID of the store.
        now: The current time (datetime object in UTC).

    Returns:
        A dictionary containing the uptime and downtime metrics for the store.
    """
    # Calculate time ranges
    last_hour_start = now - timedelta(hours=1)
    last_day_start = now - timedelta(days=1)
    last_week_start = now - timedelta(weeks=1)

    # Calculate uptime and downtime for each time range
    uptime_last_hour, downtime_last_hour = calculate_uptime_downtime(session, store_id, last_hour_start, now)
    uptime_last_day, downtime_last_day = calculate_uptime_downtime(session, store_id, last_day_start, now)
    uptime_last_week, downtime_last_week = calculate_uptime_downtime(session, store_id, last_week_start, now)

    # Return the report data
    return {
        'store_id': store_id,
        'uptime_last_hour': uptime_last_hour,
        'uptime_last_day': uptime_last_day / 60,  # Convert to hours
        'uptime_last_week': uptime_last_week / 60,  # Convert to hours
        'downtime_last_hour': downtime_last_hour,
        'downtime_last_day': downtime_last_day / 60,  # Convert to hours
        'downtime_last_week': downtime_last_week / 60  # Convert to hours
    }

def generate_report_csv(session: sessionmaker) -> str:
    """Generates the full report CSV data.

    Args:
        session: The database session.

    Returns:
        A string containing the CSV data.
    """
    # Get all unique store IDs from StoreStatus
    store_ids = session.query(StoreStatus.store_id).distinct().all()
    store_ids = [store_id[0] for store_id in store_ids]  # Extract store IDs from the result

    # Use the maximum timestamp from StoreStatus as the "current time"
    max_timestamp_utc = session.query(db.func.max(StoreStatus.timestamp_utc)).scalar()
    if max_timestamp_utc is None:
        # Handle the case where there is no data in StoreStatus
        return "No data available to generate report."
    now = max_timestamp_utc

    # Generate report data for all stores
    report_data = [generate_store_report(session, store_id, now) for store_id in store_ids]

    # Create a Pandas DataFrame
    df = pd.DataFrame(report_data)

    # Create the CSV in memory
    csv_buffer = io.StringIO()
    df.to_csv(csv_buffer, index=False)  # No index
    csv_content = csv_buffer.getvalue()
    csv_buffer.close()
    return csv_content

def load_data_from_zip(session, zip_file_path: str):
    """
    Loads data from CSV files within a zip archive into the database.
    """
    try:
        with zipfile.ZipFile(zip_file_path, 'r') as zf:
            for filename in zf.namelist():
                # Skip Mac metadata files
                if filename.startswith('__MACOSX') or filename.startswith('._'):
                    continue
                    
                if filename.endswith('.csv'):
                    print(f"Processing {filename}")
                    with zf.open(filename) as csvfile:
                        # Read binary data and decode
                        binary_data = csvfile.read()
                        text_data = binary_data.decode('utf-8-sig').replace('\x00', '')
                        csv_file = io.StringIO(text_data)
                        reader = csv.DictReader(csv_file)
                        
                        if 'store_status.csv' in filename.lower():
                            for row in reader:
                                try:
                                    timestamp_utc = datetime.strptime(
                                        row['timestamp_utc'].strip(), 
                                        '%Y-%m-%d %H:%M:%S.%f UTC'
                                    )
                                    store_status = StoreStatus(
                                        store_id=row['store_id'].strip(),
                                        timestamp_utc=timestamp_utc,
                                        status=row['status'].strip()
                                    )
                                    session.add(store_status)
                                except Exception as e:
                                    print(f"Error processing row in store_status: {e}")
                                    continue
                                    
                        elif 'menu_hours.csv' in filename.lower():
                            for row in reader:
                                try:
                                    business_hours = BusinessHours(
                                        store_id=row['store_id'].strip(),
                                        day_of_week=int(float(row['dayOfWeek'])),
                                        start_time_local=row['start_time_local'].strip(),
                                        end_time_local=row['end_time_local'].strip()
                                    )
                                    session.add(business_hours)
                                except Exception as e:
                                    print(f"Error processing row in menu_hours: {e}")
                                    continue
                                    
                        elif 'timezones.csv' in filename.lower():
                            for row in reader:
                                try:
                                    store_timezone = StoreTimezone(
                                        store_id=row['store_id'].strip(),
                                        timezone_str=row['timezone_str'].strip()
                                    )
                                    session.add(store_timezone)
                                except Exception as e:
                                    print(f"Error processing row in timezones: {e}")
                                    continue
                        
                        session.commit()
                        print(f"Completed processing {filename}")
                        
    except Exception as e:
        print(f"Error loading data: {e}")
        session.rollback()
        raise

# --- API Endpoints ---

@app.route('/trigger_report', methods=['POST'])
def trigger_report():
    """
    API endpoint to trigger the generation of a report.
    """
    try:
        report = Report()
        db.session.add(report)
        db.session.commit()
        
        # Use a thread to generate the report in the background
        report_executor.submit(generate_report_and_update_db, report.id)
        return jsonify({'report_id': report.id}), 200
    except Exception as e:
        db.session.rollback()
        print(f"Error in trigger_report: {e}")
        return jsonify({'error': 'Internal server error'}), 500

def generate_report_and_update_db(report_id: str):
    """Generates the report with progress tracking."""
    with app.app_context():  # Add application context here
        try:
            report = Report.query.get(report_id)
            if not report:
                print(f"Report with ID {report_id} not found.")
                return

            # Get max timestamp
            max_timestamp_utc = db.session.query(db.func.max(StoreStatus.timestamp_utc)).scalar()
            if not max_timestamp_utc:
                report.status = 'Error'
                db.session.commit()
                return

            # Get unique store IDs
            store_ids = db.session.query(StoreStatus.store_id).distinct().all()
            store_ids = [store_id[0] for store_id in store_ids]
            total_stores = len(store_ids)
            
            print(f"Starting report generation for {total_stores} stores...")
            
            # Process stores in batches
            batch_size = 100
            all_results = []
            
            for i in range(0, len(store_ids), batch_size):
                batch = store_ids[i:i + batch_size]
                batch_results = [
                    generate_store_report(db.session, store_id, max_timestamp_utc)
                    for store_id in batch
                ]
                all_results.extend([r for r in batch_results if r is not None])
                
                # Print progress
                progress = min(100, (i + batch_size) * 100 // total_stores)
                print(f"Progress: {progress}% ({i + len(batch)}/{total_stores} stores processed)")

            # Create DataFrame and save to CSV
            df = pd.DataFrame(all_results)
            
            # Save to a temporary file
            temp_file = tempfile.NamedTemporaryFile(mode='w+t', suffix='.csv', delete=False)
            df.to_csv(temp_file.name, index=False)
            
            # Update report status
            report = Report.query.get(report_id)
            if report:
                report.status = 'Complete'
                report.filename = os.path.basename(temp_file.name)
                db.session.commit()
            
            print(f"Report generation completed. Saved to {report.filename}")
            
        except Exception as e:
            print(f"Error generating report {report_id}: {e}")
            report = Report.query.get(report_id)
            if report:
                report.status = 'Error'
                db.session.commit()

@app.route('/get_report', methods=['GET'])
def get_report():
    """
    API endpoint to retrieve the status or the CSV data of a report.
    """
    report_id = request.args.get('report_id')
    try:
        report = db.session.get(Report, report_id)  # Updated to use session.get

        if not report:
            return jsonify({'error': 'Report not found'}), 404

        if report.status == 'Running':
            return jsonify({'status': 'Running'}), 200
        elif report.status == 'Error':
            return jsonify({'status': 'Error'}), 500
        elif report.status == 'Complete':
            file_path = os.path.join(tempfile.gettempdir(), report.filename)
            try:
                return send_file(file_path, mimetype='text/csv', as_attachment=True, download_name='report.csv')
            except FileNotFoundError:
                return jsonify({'status': 'Error', 'message': 'CSV file not found'}), 500
        else:
            return jsonify({'status': 'Unknown'}), 500
    except Exception as e:
        print(f"Error in get_report: {e}")
        return jsonify({'error': 'Internal server error'}), 500

# --- Main ---
if __name__ == '__main__':
    with app.app_context():
        # Create all database tables
        db.create_all()
        
        # Load data from the zip file
        zip_file_path = 'store-monitoring-data.zip'
        try:
            load_data_from_zip(db.session, zip_file_path)
            print("Data loaded successfully")
        except Exception as e:
            print(f"Error loading initial data: {e}")
            exit(1)

    # Run the Flask application
    app.run(debug=True, port=5000)
