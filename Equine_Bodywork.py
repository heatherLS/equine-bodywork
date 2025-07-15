import streamlit as st
from streamlit_drawable_canvas import st_canvas
from PIL import Image, ImageDraw, ImageColor
from datetime import date
import pandas as pd
import os
from dotenv import load_dotenv
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail, Attachment, FileContent, FileName, FileType, Disposition
import base64

# Load environment variables
load_dotenv()

def image_to_base64(path):
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()

def pil_to_base64(pil_img):
    from io import BytesIO
    buf = BytesIO()
    pil_img.save(buf, format="PNG")
    byte_data = buf.getvalue()
    return f"data:image/png;base64,{base64.b64encode(byte_data).decode()}"

def export_canvas_to_file(canvas_data, background_image, save_path):
    if not canvas_data.json_data or "objects" not in canvas_data.json_data:
        return

    img = background_image.convert("RGBA")
    draw = ImageDraw.Draw(img)

    for obj in canvas_data.json_data["objects"]:
        if obj.get("type") == "path":
            try:
                stroke = obj.get("stroke", "#ff0000")
                stroke_width = int(obj.get("strokeWidth", 3))
                color = ImageColor.getrgb(stroke) + (255,)

                path_points = []
                for segment in obj.get("path", []):
                    cmd = segment[0]
                    coords = segment[1:]
                    if cmd in ["M", "L"]:
                        path_points.append((coords[0], coords[1]))
                    elif cmd == "Q":
                        path_points.append((coords[2], coords[3]))

                if len(path_points) > 1:
                    draw.line(path_points, fill=color, width=stroke_width)

            except Exception as e:
                print("⚠️ Error drawing path:", e)

    img.save(save_path)

def encode_file(path):
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()

def send_session_email(to_email, horse_name, session_date, amount, paid, notes, left_path, right_path):
    from_email = os.getenv("FROM_EMAIL")
    from_name = os.getenv("FROM_NAME")
    api_key = os.getenv("SENDGRID_API_KEY")

    paid_status = "✅ Paid" if paid else "❌ Not Paid"
    notes_html = notes.replace('\n', '<br>')

    # GitHub-hosted logo
    logo_url = "https://raw.githubusercontent.com/heatherLS/equine-bodywork/main/images/logo.png"

    html_content = f"""
    <img src="{logo_url}" alt="Logo" style="height:100px;"><br><br>
    <h2>🐴 Session Summary for {horse_name}</h2>
    <p><strong>Date:</strong> {session_date}</p>
    <p><strong>Amount:</strong> ${amount:.2f} — {paid_status}</p>
    <p><strong>Notes:</strong></p>
    <p>{notes_html}</p>
    <h3>📎 Marked Areas of Concern</h3>
    <p>The marked diagrams are attached as images of the left and right sides of the horse.</p>
    """

    message = Mail(
        from_email=(from_email, from_name),
        to_emails=to_email,
        subject=f"Session Summary: {horse_name} ({session_date})",
        html_content=html_content,
    )

    # Set reply-to manually
    message.reply_to = "allisonk330@gmail.com"

    # Attach both PNGs
    attachments = []
    for path, label in [(left_path, "left"), (right_path, "right")]:
        if os.path.exists(path):
            encoded = encode_file(path)
            attachment = Attachment(
                FileContent(encoded),
                FileName(f"{horse_name}_{label}.png"),
                FileType("image/png"),
                Disposition("attachment")
            )
            attachments.append(attachment)

    message.attachment = attachments

    try:
        sg = SendGridAPIClient(api_key)
        sg.send(message)
        return True
    except Exception as e:
        st.error("📋 SendGrid error:")
        st.exception(e)
        return False

# --- Streamlit UI ---
st.set_page_config(page_title="🐴 Equine Bodywork Tracker", layout="wide")
st.title("🐴 Equine Bodywork Session Tracker")
os.makedirs("data", exist_ok=True)

# Load background images
left_img_path = "images/horse_left.png"
right_img_path = "images/horse_right.png"

left_img = Image.open(left_img_path)
right_img = Image.open(right_img_path)

left_bg_url = pil_to_base64(left_img)
right_bg_url = pil_to_base64(right_img)

# Sidebar inputs
st.sidebar.header("Session Info")
horse_name = st.sidebar.text_input("Horse Name")
session_date = st.sidebar.date_input("Date", value=date.today())
amount = st.sidebar.number_input("Amount Charged ($)", min_value=0.0, step=1.0)
paid = st.sidebar.checkbox("Paid?")
client_email = st.sidebar.text_input("Client Email (optional)")
notes = st.sidebar.text_area("Session Notes & Recommendations", height=150)

# Canvas Drawing
st.subheader("📌 Mark Areas of Concern")
col1, col2 = st.columns(2)
with col1:
    st.markdown("**Left Side**")
    canvas_left = st_canvas(
        fill_color="rgba(255, 0, 0, 0.3)",
        stroke_width=3,
        height=left_img.height,
        width=left_img.width,
        background_image=left_img,  # ✅ Local file included in repo
        drawing_mode="freedraw",
        key="canvas_left"
    )
with col2:
    st.markdown("**Right Side**")
    canvas_right = st_canvas(
        fill_color="rgba(255, 0, 0, 0.3)",
        stroke_width=3,
        height=right_img.height,
        width=right_img.width,
        background_image=right_img,  # ✅ Local file included in repo
        drawing_mode="freedraw",
        key="canvas_right"
    )


# Save and Send
if st.button("💾 Save Session"):
    session_data = {
        "Date": session_date,
        "Horse": horse_name,
        "Amount": amount,
        "Paid": paid,
        "Email": client_email,
        "Notes": notes
    }

    csv_path = "data/session_data.csv"
    df = pd.DataFrame([session_data])
    if os.path.exists(csv_path):
        existing = pd.read_csv(csv_path)
        df = pd.concat([existing, df], ignore_index=True)
    df.to_csv(csv_path, index=False)
    st.success("✅ Session saved!")

    # Save annotated images
    left_path = f"data/{horse_name}_left.png"
    right_path = f"data/{horse_name}_right.png"
    export_canvas_to_file(canvas_left, left_img, left_path)
    export_canvas_to_file(canvas_right, right_img, right_path)

    # Send email
    if client_email:
        sent = send_session_email(client_email, horse_name, session_date, amount, paid, notes, left_path, right_path)
        if sent:
            st.success("📧 Email sent to client!")
        else:
            st.warning("⚠️ Email failed to send.")
