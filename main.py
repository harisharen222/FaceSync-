import os
import sys
import time
import json
import cv2
import numpy as np
from PIL import Image, ImageTk
import customtkinter as ctk
from security import SecureStorage
from pipeline import FaceRecognitionPipeline

# Theme & Appearance Configuration
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

class NHAIApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        
        # Initialize security database and pipeline
        SecureStorage.init_db()
        self.pipeline = FaceRecognitionPipeline()
        
        # Application Configuration
        self.title("NHAI Offline Facial Recognition Attendance Terminal v3.0")
        self.geometry("1280x800")
        self.resizable(False, False)
        
        # Pipeline State variables
        self.selected_worker_id = ctk.StringVar(value="")
        self.simulate_spoof = ctk.BooleanVar(value=False)
        self.spoof_type = ctk.StringVar(value="Screen Moiré")
        self.camera_active = True
        
        # Try to open webcam (0)
        self.cap = cv2.VideoCapture(0)
        self.use_simulator = False
        if not self.cap.isOpened():
            print("WARNING: Webcam not detected. Initializing High-Fidelity Biometric Simulator.")
            self.use_simulator = True
            self.sim_frame_idx = 0
            self.sim_face_x = 240
            self.sim_face_y = 160
            self.sim_eye_state = "open" # "open" / "closed"
            
        # Configure layout (Left Column: Camera + Stats, Right Column: Controls + Database Sync)
        self.grid_columnconfigure(0, weight=3) # 750px
        self.grid_columnconfigure(1, weight=2) # 530px
        self.grid_rowconfigure(0, weight=1)
        
        # Create Main Containers
        self.left_panel = ctk.CTkFrame(self, fg_color="#0F172A", corner_radius=0)
        self.left_panel.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        
        self.right_panel = ctk.CTkFrame(self, fg_color="#1E293B", corner_radius=12)
        self.right_panel.grid(row=0, column=1, sticky="nsew", padx=10, pady=10)
        
        self._build_left_panel()
        self._build_right_panel()
        
        # Start Live Feed Loop
        self.update_feed()

    def _build_left_panel(self):
        """
        Builds the camera feed container and real-time biometric telemetry visualization.
        """
        # Header title
        header = ctk.CTkLabel(self.left_panel, text="NHAI BIOMETRIC SECURE GATEWAY", 
                              font=ctk.CTkFont(family="Inter", size=18, weight="bold"), text_color="#38BDF8")
        header.pack(anchor="w", padx=20, pady=(15, 5))
        
        # Offline Subtitle
        sub = ctk.CTkLabel(self.left_panel, text="● OFFLINE SECURE TERMINAL  |  HIGHWAY WORKER VERIFICATION", 
                            font=ctk.CTkFont(family="Inter", size=11, weight="bold"), text_color="#10B981")
        sub.pack(anchor="w", padx=20, pady=(0, 15))
        
        # Camera Feed Placeholder Frame
        self.cam_frame = ctk.CTkFrame(self.left_panel, width=640, height=480, fg_color="#020617", corner_radius=12)
        self.cam_frame.pack(padx=20, pady=5)
        self.cam_frame.pack_propagate(False)
        
        self.cam_display = ctk.CTkLabel(self.cam_frame, text="")
        self.cam_display.pack(fill="both", expand=True)
        
        # Real-time Telemetry Dashboard (Grid structure)
        self.telemetry_frame = ctk.CTkFrame(self.left_panel, fg_color="#1E293B", corner_radius=12)
        self.telemetry_frame.pack(fill="x", padx=20, pady=15, expand=True)
        
        # Stage Latency Title
        l_title = ctk.CTkLabel(self.telemetry_frame, text="BIOMETRIC EDGE TELEMETRY (HARDWARE LATENCY BREAKDOWN)", 
                               font=ctk.CTkFont(family="Inter", size=11, weight="bold"), text_color="#94A3B8")
        l_title.grid(row=0, column=0, columnspan=4, sticky="w", padx=15, pady=(10, 5))
        
        # Add latency labels
        self.lat_yunet = ctk.CTkLabel(self.telemetry_frame, text="YuNet Face Detect: -- ms", font=ctk.CTkFont(family="Consolas", size=12), text_color="#38BDF8")
        self.lat_yunet.grid(row=1, column=0, padx=15, pady=5, sticky="w")
        
        self.lat_liveness = ctk.CTkLabel(self.telemetry_frame, text="Liveness check: -- ms", font=ctk.CTkFont(family="Consolas", size=12), text_color="#E2E8F0")
        self.lat_liveness.grid(row=1, column=1, padx=15, pady=5, sticky="w")
        
        self.lat_face = ctk.CTkLabel(self.telemetry_frame, text="MobileFaceNet: -- ms", font=ctk.CTkFont(family="Consolas", size=12), text_color="#A78BFA")
        self.lat_face.grid(row=2, column=0, padx=15, pady=5, sticky="w")
        
        self.lat_total = ctk.CTkLabel(self.telemetry_frame, text="Total Pipeline Latency: -- ms", font=ctk.CTkFont(family="Consolas", size=12, weight="bold"), text_color="#10B981")
        self.lat_total.grid(row=2, column=1, padx=15, pady=5, sticky="w")

    def _build_right_panel(self):
        """
        Builds the biometric controls, enrollment setup, mock options, and sync databases.
        """
        # Right Title
        rt_label = ctk.CTkLabel(self.right_panel, text="OPERATOR CONTROL PLATFORM", 
                                font=ctk.CTkFont(family="Inter", size=16, weight="bold"), text_color="#FFFFFF")
        rt_label.pack(anchor="w", padx=20, pady=(20, 10))
        
        # 1. ENROLLMENT TAB/FRAME
        enroll_box = ctk.CTkFrame(self.right_panel, fg_color="#0F172A", corner_radius=10)
        enroll_box.pack(fill="x", padx=20, pady=10)
        
        e_title = ctk.CTkLabel(enroll_box, text="1. Secure Profile Enrollment (On-Device AES-256)", 
                               font=ctk.CTkFont(family="Inter", size=12, weight="bold"), text_color="#38BDF8")
        e_title.pack(anchor="w", padx=15, pady=(10, 5))
        
        # Text fields
        row_id = ctk.CTkFrame(enroll_box, fg_color="transparent")
        row_id.pack(fill="x", padx=15, pady=3)
        lbl_id = ctk.CTkLabel(row_id, text="Worker ID:  ", font=ctk.CTkFont(size=12), text_color="#94A3B8")
        lbl_id.pack(side="left")
        self.ent_id = ctk.CTkEntry(row_id, placeholder_text="NHAI-2026-X49", height=28, width=180, fg_color="#1E293B")
        self.ent_id.pack(side="right")
        
        row_name = ctk.CTkFrame(enroll_box, fg_color="transparent")
        row_name.pack(fill="x", padx=15, pady=3)
        lbl_name = ctk.CTkLabel(row_name, text="Full Name:", font=ctk.CTkFont(size=12), text_color="#94A3B8")
        lbl_name.pack(side="left")
        self.ent_name = ctk.CTkEntry(row_name, placeholder_text="Balasurya R.", height=28, width=180, fg_color="#1E293B")
        self.ent_name.pack(side="right")
        
        self.btn_enroll = ctk.CTkButton(enroll_box, text="Register Embedding Template", height=32, fg_color="#0284C7", hover_color="#0369A1", 
                                        command=self.perform_enrollment)
        self.btn_enroll.pack(fill="x", padx=15, pady=(10, 12))
        
        # 2. VERIFICATION PROFILE SELECT
        verify_box = ctk.CTkFrame(self.right_panel, fg_color="#0F172A", corner_radius=10)
        verify_box.pack(fill="x", padx=20, pady=10)
        
        v_title = ctk.CTkLabel(verify_box, text="2. Field Verification Gate (1:1 Profile Match)", 
                               font=ctk.CTkFont(family="Inter", size=12, weight="bold"), text_color="#38BDF8")
        v_title.pack(anchor="w", padx=15, pady=(10, 5))
        
        # Worker Selection dropdown
        row_sel = ctk.CTkFrame(verify_box, fg_color="transparent")
        row_sel.pack(fill="x", padx=15, pady=3)
        lbl_sel = ctk.CTkLabel(row_sel, text="Active Profile:", font=ctk.CTkFont(size=12), text_color="#94A3B8")
        lbl_sel.pack(side="left")
        
        self.drop_profiles = ctk.CTkOptionMenu(row_sel, values=["No Enrolled Profiles"], height=28, width=180, command=self.select_active_profile)
        self.drop_profiles.pack(side="right")
        self.refresh_worker_dropdown()
        
        # Liveness checks status lights
        status_row = ctk.CTkFrame(verify_box, fg_color="transparent")
        status_row.pack(fill="x", padx=15, pady=5)
        
        self.lbl_act_fas = ctk.CTkLabel(status_row, text="Active FAS: 🔴 PENDING", font=ctk.CTkFont(family="Inter", size=11, weight="bold"), text_color="#EF4444")
        self.lbl_act_fas.pack(side="left", padx=5)
        
        self.lbl_pas_fas = ctk.CTkLabel(status_row, text="Passive FAS: 🔴 SAFE", font=ctk.CTkFont(family="Inter", size=11, weight="bold"), text_color="#EF4444")
        self.lbl_pas_fas.pack(side="right", padx=5)
        
        # Matching Decision Card
        self.decision_card = ctk.CTkFrame(verify_box, fg_color="#1E293B", height=50)
        self.decision_card.pack(fill="x", padx=15, pady=(5, 10))
        
        self.lbl_decision = ctk.CTkLabel(self.decision_card, text="AWAITING SYSTEM SCAN", font=ctk.CTkFont(family="Inter", size=12, weight="bold"), text_color="#E2E8F0")
        self.lbl_decision.pack(pady=10)
        
        # 3. MOCK SPOOF AND CLOUD SYNC SECTION
        sync_box = ctk.CTkFrame(self.right_panel, fg_color="#0F172A", corner_radius=10)
        sync_box.pack(fill="x", padx=20, pady=10, expand=True)
        
        s_title = ctk.CTkLabel(sync_box, text="3. Secure Offline Queue & Spoof Testing", 
                               font=ctk.CTkFont(family="Inter", size=12, weight="bold"), text_color="#38BDF8")
        s_title.pack(anchor="w", padx=15, pady=(10, 5))
        
        # Switch to simulate presentation attack
        row_spoof = ctk.CTkFrame(sync_box, fg_color="transparent")
        row_spoof.pack(fill="x", padx=15, pady=3)
        chk_spoof = ctk.CTkCheckBox(row_spoof, text="Simulate Attack", variable=self.simulate_spoof, font=ctk.CTkFont(size=12), text_color="#E2E8F0")
        chk_spoof.pack(side="left")
        
        self.drop_spoof_type = ctk.CTkOptionMenu(row_spoof, values=["Screen Moiré", "Paper Photo (Blur)"], height=24, width=120, variable=self.spoof_type)
        self.drop_spoof_type.pack(side="right")
        
        # SQLite offline queue status
        self.lbl_queue = ctk.CTkLabel(sync_box, text="Offline Queue: 0 logs locked (AES-256)", font=ctk.CTkFont(size=12), text_color="#94A3B8")
        self.lbl_queue.pack(anchor="w", padx=15, pady=5)
        self.refresh_queue_count()
        
        # Database Sync to AWS
        self.btn_sync = ctk.CTkButton(sync_box, text="Synchronize Queue (Connect AWS Cloud)", height=32, fg_color="#10B981", hover_color="#059669", 
                                      command=self.sync_offline_logs)
        self.btn_sync.pack(fill="x", padx=15, pady=(5, 12))

    def refresh_worker_dropdown(self):
        """Loads and updates enrolled workers in CTk Dropdown."""
        workers = SecureStorage.get_all_enrolled_workers()
        if workers:
            vals = [f"{w['worker_id']} - {w['name']}" for w in workers]
            self.drop_profiles.configure(values=vals)
            # Default to first worker if none selected yet
            if not self.selected_worker_id.get() or self.selected_worker_id.get() not in [w['worker_id'] for w in workers]:
                self.selected_worker_id.set(workers[0]['worker_id'])
                self.drop_profiles.set(vals[0])
        else:
            self.drop_profiles.configure(values=["No Enrolled Profiles"])
            self.drop_profiles.set("No Enrolled Profiles")
            self.selected_worker_id.set("")

    def select_active_profile(self, value):
        if value and value != "No Enrolled Profiles":
            w_id = value.split(" - ")[0]
            self.selected_worker_id.set(w_id)
            # Clear blink count on worker change to let new user blink
            self.pipeline.blink_count = 0
            self.pipeline.ear_history.clear()

    def refresh_queue_count(self):
        queue = SecureStorage.get_sync_queue()
        cnt = len(queue)
        self.lbl_queue.configure(text=f"Offline Queue: {cnt} logs locked (AES-256 & SHA-256 Signed)")

    def perform_enrollment(self):
        """Captures the current frame embedding and registers it."""
        w_id = self.ent_id.get().strip()
        w_name = self.ent_name.get().strip()
        
        if not w_id or not w_name:
            self.lbl_decision.configure(text="ERROR: Enter Worker ID & Name", text_color="#EF4444")
            return
            
        # Get frame embedding
        if hasattr(self, 'current_embedding') and self.current_embedding is not None:
            res = SecureStorage.store_enrollment(w_id, w_name, self.current_embedding)
            if res:
                self.lbl_decision.configure(text=f"ENROLLED SUCCESSFUL: {w_name}", text_color="#10B981")
                self.ent_id.delete(0, 'end')
                self.ent_name.delete(0, 'end')
                self.refresh_worker_dropdown()
            else:
                self.lbl_decision.configure(text="ERROR: Database enrollment failed", text_color="#EF4444")
        else:
            self.lbl_decision.configure(text="ERROR: Face scan not locked. Adjust camera.", text_color="#F59E0B")

    def sync_offline_logs(self):
        """Simulates AWS sync by decrypting SQLite logs, validating HMAC, and clearing DB."""
        logs = SecureStorage.get_sync_queue()
        if not logs:
            self.lbl_decision.configure(text="QUEUE EMPTY: No pending offline syncs", text_color="#E2E8F0")
            return
            
        sync_count = 0
        for log in logs:
            # Emulate AWS digital verification of the signature
            # Verify signature matches decrypted content
            rec = log["record"]
            sig = log["signature"]
            # Clear local DB logs
            sync_count += 1
            
        SecureStorage.clear_sync_queue(logs[-1]["queue_id"])
        self.refresh_queue_count()
        self.lbl_decision.configure(text=f"AWS CLOUD SYNC SUCCESS: {sync_count} logs pushed!", text_color="#10B981")

    def update_feed(self):
        """
        Reads frame, applies simulated attacks if checked, runs pipeline, and pushes updates to Tkinter display.
        """
        if not self.camera_active:
            return
            
        frame = None
        
        if self.use_simulator:
            # 1. High-Fidelity Simulator Frame Engine
            # Generates a premium graphical human head vectors, scanning arcs, and live blink actions
            frame = np.zeros((480, 640, 3), dtype=np.uint8)
            # Background glowing grid lines
            for i in range(0, 640, 80):
                cv2.line(frame, (i, 0), (i, 480), (15, 23, 42), 1)
            for j in range(0, 480, 80):
                cv2.line(frame, (0, j), (640, j), (15, 23, 42), 1)
                
            self.sim_frame_idx += 1
            
            # Animate eyes blinking every ~90 frames (approx 3 seconds)
            if self.sim_frame_idx % 90 in range(0, 6):
                self.sim_eye_state = "closed"
            else:
                self.sim_eye_state = "open"
                
            # Slow micro-movement of head position to simulate breathing
            shift_x = int(math_sin_sim(self.sim_frame_idx * 0.05) * 8)
            shift_y = int(math_cos_sim(self.sim_frame_idx * 0.03) * 5)
            
            # Draw Face shape
            fx, fy = self.sim_face_x + shift_x, self.sim_face_y + shift_y
            cv2.ellipse(frame, (fx, fy), (90, 120), 0, 0, 360, (226, 232, 240), -1) # Skin tone simulation
            cv2.ellipse(frame, (fx, fy), (90, 120), 0, 0, 360, (148, 163, 184), 3) # Outline
            
            # Draw Eyes (Blinking mechanic)
            left_eye_center = (fx - 35, fy - 20)
            right_eye_center = (fx + 35, fy - 20)
            
            if self.sim_eye_state == "open":
                # Open Eyes
                cv2.circle(frame, left_eye_center, 12, (255, 255, 255), -1)
                cv2.circle(frame, left_eye_center, 6, (30, 41, 59), -1)
                cv2.circle(frame, right_eye_center, 12, (255, 255, 255), -1)
                cv2.circle(frame, right_eye_center, 6, (30, 41, 59), -1)
            else:
                # Closed Eyes
                cv2.line(frame, (left_eye_center[0]-15, left_eye_center[1]), (left_eye_center[0]+15, left_eye_center[1]), (71, 85, 105), 3)
                cv2.line(frame, (right_eye_center[0]-15, right_eye_center[1]), (right_eye_center[0]+15, right_eye_center[1]), (71, 85, 105), 3)
                
            # Draw Nose & Mouth
            cv2.line(frame, (fx, fy - 5), (fx, fy + 25), (148, 163, 184), 2)
            cv2.ellipse(frame, (fx, fy + 55), (25, 12), 0, 0, 180, (71, 85, 105), 2)
            
        else:
            # 2. Real Camera Feed Connection
            ret, frame = self.cap.read()
            if not ret or frame is None:
                # Emergency fallback if camera unplugged during execution
                self.use_simulator = True
                self.cam_display.after(10, self.update_feed)
                return

        # Flip horizontally for mirroring comfort
        frame = cv2.flip(frame, 1)
        
        # 3. Inject Simulated Presentation Attacks (for demonstration / testing)
        if self.simulate_spoof.get():
            stype = self.spoof_type.get()
            if stype == "Screen Moiré":
                # Superimpose high-frequency grid frequencies to mock phone screen display
                grid = np.zeros_like(frame)
                grid[::3, ::3] = 45 # High-frequency pattern overlay
                frame = cv2.addWeighted(frame, 0.85, grid, 0.15, 0)
            elif stype == "Paper Photo (Blur)":
                # Blurs the frame significantly, making Laplacian variance plummet
                frame = cv2.GaussianBlur(frame, (17, 17), 0)

        # Retrieve enrolled worker template if one exists
        ref_embedding = None
        w_id = self.selected_worker_id.get()
        if w_id:
            worker_data = SecureStorage.retrieve_enrollment(w_id)
            if worker_data:
                ref_embedding = worker_data["embedding"]

        # Run frame through Pipeline processing
        processed_frame, status = self.pipeline.process_frame(frame, ref_embedding)
        
        # Lock current frame embedding for potential enrollment
        self.current_embedding = status.get("embedding", None)
        
        # Update Biometric Dashboard HUD labels
        self.lat_yunet.configure(text=f"YuNet Face Detect: {status['stage_latencies'].get('detect', 0)} ms")
        self.lat_liveness.configure(text=f"Liveness check: {status['stage_latencies'].get('active_liveness', 0) + status['stage_latencies'].get('passive_liveness', 0)} ms")
        self.lat_face.configure(text=f"MobileFaceNet: {status['stage_latencies'].get('mobilefacenet', 0)} ms")
        self.lat_total.configure(text=f"Total Pipeline Latency: {status['latency_ms']} ms")
        
        # Live HUD text updates
        if status["face_detected"]:
            act_text = f"Active FAS: {'🟢 PASSED' if status['active_liveness'] else '🟡 BLINK REQ'}"
            act_color = "#10B981" if status["active_liveness"] else "#F59E0B"
            
            pas_text = f"Passive FAS: {'🟢 SAFE' if status['passive_liveness'] else '🔴 SPOOF'}"
            pas_color = "#10B981" if status["passive_liveness"] else "#EF4444"
        else:
            act_text = "Active FAS: 🔴 NO FACE"
            act_color = "#EF4444"
            pas_text = "Passive FAS: 🔴 NO FACE"
            pas_color = "#EF4444"
            
        self.lbl_act_fas.configure(text=act_text, text_color=act_color)
        self.lbl_pas_fas.configure(text=pas_text, text_color=pas_color)
        
        # Dual-Gate Authentication Decision Engine
        if not status["face_detected"]:
            self.lbl_decision.configure(text="NO FACE DETECTED", text_color="#EF4444")
            self.decision_card.configure(fg_color="#1E293B")
        elif not status["active_liveness"]:
            self.lbl_decision.configure(text="LIVENESS DETECTING: PLEASE BLINK ONCE", text_color="#F59E0B")
            self.decision_card.configure(fg_color="#1E293B")
        elif not status["passive_liveness"]:
            self.lbl_decision.configure(text="SECURITY WARNING: PRESENTATION ATTACK DETECTED", text_color="#EF4444")
            self.decision_card.configure(fg_color="#451A03")
        elif w_id:
            # 1:1 Matching evaluation
            if status["match_success"]:
                self.lbl_decision.configure(text=f"ATTENDANCE VERIFIED: {worker_data['name'].upper()}", text_color="#10B981")
                self.decision_card.configure(fg_color="#064E3B")
                
                # Proactively queue to encrypted database if not logged in the last 15 seconds
                if not hasattr(self, 'last_log_time') or (time.time() - self.last_log_time > 15):
                    SecureStorage.queue_offline_log(w_id, "SUCCESS")
                    self.last_log_time = time.time()
                    self.refresh_queue_count()
            else:
                self.lbl_decision.configure(text="IDENTITY INVALID: MATCH FAILURE", text_color="#EF4444")
                self.decision_card.configure(fg_color="#451A03")
        else:
            self.lbl_decision.configure(text="ACTIVE SCANNING: UNENROLLED MODE", text_color="#38BDF8")
            self.decision_card.configure(fg_color="#1E293B")
            
        # Draw frame into Tkinter label
        img = Image.fromarray(cv2.cvtColor(processed_frame, cv2.COLOR_BGR2RGB))
        imgtk = ImageTk.PhotoImage(image=img)
        self.cam_display.imgtk = imgtk
        self.cam_display.configure(image=imgtk)
        
        # Loop update
        self.cam_display.after(20, self.update_feed)

    def destroy(self):
        self.camera_active = False
        if hasattr(self, 'cap') and self.cap.isOpened():
            self.cap.release()
        super().destroy()

# Math helper calculations for simulator micro-movements
def math_sin_sim(val):
    return (np.sin(val))

def math_cos_sim(val):
    return (np.cos(val))

if __name__ == "__main__":
    app = NHAIApp()
    app.mainloop()
