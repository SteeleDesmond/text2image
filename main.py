import os
import queue
import time
from threading import Thread

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import requests
from openai import OpenAI

from tkinter import Tk, Label
from PIL import Image, ImageTk


class FileModifiedHandler(FileSystemEventHandler):
    def __init__(self, filename, callback):
        self.filename = filename
        self.callback = callback

    def on_modified(self, event):
        if event.src_path == self.filename:
            self.callback()


class GemStoneMonitor:

    def __init__(self, gui_queue):
        api_key = os.getenv("OPENAI_API_KEY", "setme")
        self.client = OpenAI(api_key=api_key)

        self.room_dir = "C:\\Users\\Steele Desmond\\Desktop\\Lich5\\scripts\\custom\\rooms"
        self.room_desc_dir = os.path.join(self.room_dir, "room_descriptions")
        self.room_image_dir = os.path.join(self.room_dir, "room_images")
        self.current_room_file_path = os.path.join(self.room_dir, 'current_room.txt')

        self.last_run = 0  # Timestamp of the last run of handle_file_change
        self.room_image_map = {}  # room_description_file_path: room_image_file_path

        self.gui_queue = gui_queue

    def start(self):
        self.monitor_file_for_changes(self.current_room_file_path, self.handle_file_change)

    def monitor_file_for_changes(self, file_path, callback):
        directory = os.path.dirname(file_path)
        filename = os.path.basename(file_path)

        # Start the watchdog file observer (similar to linux epoll I think)
        event_handler = FileModifiedHandler(file_path, callback)
        observer = Observer()
        observer.schedule(event_handler, directory, recursive=False)
        observer.start()

        try:
            while True:
                # print('polling')
                time.sleep(0.1)
        except KeyboardInterrupt:
            observer.stop()
        observer.join()

    def handle_file_change(self):
        current_time = time.time()
        if current_time - self.last_run < 1:  # Debounce period of 1 second
            return
        self.last_run = current_time

        if not os.path.exists(self.current_room_file_path):
            print("Current room file not found.")
            return

        room_desc_file_path = open(self.current_room_file_path, 'r').read().strip()
        if not os.path.exists(room_desc_file_path):
            print(f"Room description file does not exist: {room_desc_file_path}")

        room_image_file_path = room_desc_file_path.replace('.txt', '.png')
        room_image_path = os.path.join(self.room_image_dir, os.path.basename(room_image_file_path))
        print(f'room_image_path: {room_image_path}')

        room_desc = open(room_desc_file_path, 'r').read().strip()
        # print(f"Room description: {room_desc}")
        prompt = create_prompt(room_desc)
        print(f'prompt: {prompt}')

        if not os.path.exists(room_image_path):
            self.generate_and_save_image(prompt=prompt, file_path=room_image_path)

        # Enqueue the path for GUI update
        self.gui_queue.put(room_image_path)

    def generate_and_save_image(self, prompt, n=1, size="1024x1024", quality="standard",
                                file_path="generated_image.png"):
        """
        Generate an image using the DALL-E 3 model and save it to a local file.
        Parameters:
        - client: The OpenAI client instance.
        - prompt: The text prompt to generate images for.
        - n: The number of images to generate (default is 1).
        - size: The resolution of the generated images (default is "1024x1024").
        - quality: The quality of the generated images ("standard" or "hd").
        - file_path: The local file path to save the generated image (default is "generated_image.png").
        Returns:
        The file path of the saved image or None if an error occurred.
        """
        print('generating image')
        try:
            response = self.client.images.generate(
                model="dall-e-3",
                prompt=prompt,
                n=n,
                size=size,
                quality=quality,
                style='vivid'
            )
            # Assuming the response structure follows the provided documentation; may need adjustments.
            if response.data:
                image_url = response.data[0].url
                # Download the image content
                image_response = requests.get(image_url)
                # print(f'revised prompt: {image_response.}')
                if image_response.status_code == 200:
                    # Save the image to a file
                    with open(file_path, 'wb') as file:
                        file.write(image_response.content)
                    print(f"Image saved to {file_path}")
                    return file_path
                else:
                    print("Failed to download the image.")
                    return None
            else:
                print("No images returned from the API.")
                return None
        except Exception as e:
            print(f"An error occurred: {e}")
            return None


def run_gui(gui_queue):
    window = Tk()
    window.title("Room Image Display")
    label = None  # Initialize label variable outside of update_gui to make it accessible for modification

    def update_gui():
        nonlocal label  # Use nonlocal to modify the label variable outside the nested function
        try:
            image_path = gui_queue.get_nowait()  # Try to get an image path from the queue
            image = Image.open(image_path)
            image = image.resize((512, 512))
            photo = ImageTk.PhotoImage(image)

            # If a label already exists, destroy it to clear the previous image
            if label is not None:
                label.destroy()

            label = Label(window, image=photo)
            label.image = photo  # Keep a reference to avoid garbage collection
            label.pack()

        except queue.Empty:
            pass
        finally:
            window.after(500, update_gui)  # Schedule the next call

    update_gui()  # Start the GUI update loop
    window.mainloop()


def create_prompt(room_desc):
    prompt = (
              f'Setting: Medieval, Magic, Fantasy, Hyper-realistic, HD'
              f'\n{room_desc}')
    return prompt


if __name__ == '__main__':
    gui_queue = queue.Queue()
    monitor = GemStoneMonitor(gui_queue)

    observer_thread = Thread(target=monitor.start)
    observer_thread.start()

    run_gui(gui_queue)  # Run the GUI in the main thread
