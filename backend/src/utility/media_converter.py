import subprocess
import logging
import os

class MediaConverter:
    def __init__(self, ffmpeg_path):
        self.logger = logging.getLogger("MediaConverter")
        self.ffmpeg = ffmpeg_path

    def convert(self, input_path, output_format, output_dir=None):
        if not self.ffmpeg or not os.path.exists(self.ffmpeg):
            return {"error": "FFmpeg not found"}
            
        if not os.path.exists(input_path):
            return {"error": "Input file not found"}
            
        base_name = os.path.splitext(os.path.basename(input_path))[0]
        
        if output_dir:
            if not os.path.exists(output_dir):
                os.makedirs(output_dir)
            output_path = os.path.join(output_dir, f"{base_name}.{output_format}")
        else:
            base, ext = os.path.splitext(input_path)
            output_path = f"{base}.{output_format}"
        
        try:
            cmd = [self.ffmpeg, "-i", input_path, output_path, "-y"]
            subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
            return {"status": "success", "output": output_path}
        except subprocess.CalledProcessError as e:
            return {"error": str(e)}
