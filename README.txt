STAYWISE HOTEL MANAGEMENT SYSTEM — LOCAL DEMO

FAST SETUP (Windows / Visual Studio)

1. Extract the ZIP to a folder, for example:
   C:\Users\YourName\source\HotelManagementSystem

2. Open Visual Studio. Choose File > Open > Folder and select the extracted folder.
   You can also run the commands below in Command Prompt/Terminal after changing to the folder.

3. Install dependencies:
   python -m pip install -r requirements.txt

4. Run:
   python app.py

5. Open this address in Chrome:
   http://127.0.0.1:5000

DEMO ACCOUNTS
Admin:        admin / admin123
Manager:      manager / manager123
Receptionist: reception / reception123
Billing:      billing / billing123

The SQLite database hotel.db is created automatically on the first run and sample rooms are inserted.
To reset the demo data, stop the app and delete hotel.db. Restart app.py to recreate the database.
WARNING: deleting hotel.db permanently deletes all records stored in this local demo.

DEMO FLOW
1. Sign in as admin.
2. Open Rooms and inspect sample rooms; add a room if desired.
3. Open Guests and register a guest.
4. Open Reservations and create a booking for future dates.
5. Click Check in on that booking.
6. Open Billing & payments, record the estimated bill/payment.
7. Return to Reservations and click Check out.
8. Open Reports to show occupancy, booking status and recorded paid revenue.
9. Open User accounts as admin to demonstrate role-based access.

PROJECT SCOPE / LIMITATIONS
- Local single-computer demonstration; no public hosting or multi-computer synchronization.
- Payments are records only; no real payment gateway or actual money transfer.
- Email notifications, customer self-service portal, advanced analytics and restaurant/payroll/inventory features are not implemented.
- Demo credentials are for classroom use only. Change the secret key and passwords before any real deployment.
- A role's visible pages and route access are restricted, but this is an academic prototype, not a security-audited production system.
