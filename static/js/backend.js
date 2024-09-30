/**
 * This script handles the uploading and processing of audio/video and text files.
 * Workflow:
 * 1. Users can upload audio/video files which are then sent to Azure Video Indexer for processing.
 * 2. Users can upload text files directly.
 * 3. Users can trigger a transformation on the uploaded content which involves translating the text.
 * 4. The processed results (translated text) can be downloaded.
 */

document.addEventListener("DOMContentLoaded", function () {
   // Variable to store the text content obtained from Azure Video Indexer or uploaded by the user
   var uploadedTextContent = "";

   // Check if the "Load Audio" button is present and set up its event handler
   var loadAudioBtn = document.getElementById('loadAudioBtn');
   if (loadAudioBtn) {
      loadAudioBtn.addEventListener('click', function () {
         var input = document.createElement('input');
         input.type = 'file';
         input.accept = 'video/*, audio/*';
         input.onchange = async e => {
            var uploadedFile = e.target.files[0];
            var formData = new FormData();
            formData.append('file', uploadedFile);

            try {
               var uploadResponse = await fetch('/upload', {
                  method: 'POST',
                  body: formData,
               });
               if (!uploadResponse.ok) {
                  throw new Error(`HTTP error! Status: ${uploadResponse.status}`);
               }
               var data = await uploadResponse.json();
               console.log('Video uploaded. Processing started. Video ID:', data.videoId);
               alert("Upload successful! Processing started.");
               getProcessingResults(data.videoId);
            } catch (error) {
               console.error('Error during upload:', error);
               alert("Failed to upload and process video.");
            }
         };
         input.click();
      });
   }

   // Poll the processing results for the uploaded video
   function getProcessingResults(videoId) {
      fetch(`/results/${videoId}`)
         .then(response => {
            if (!response.ok) throw new Error('Failed to fetch results with status: ' + response.status);
            return response.json();
         })
         .then(data => {
            if (data.processingComplete) {
               console.log('Processing complete. Video results:', data.results);
               alert('Video processing completed successfully!');
            } else {
               console.log('Processing still underway...');
               setTimeout(() => getProcessingResults(videoId), 5000);
            }
         })
         .catch(error => {
            console.error('Error during processing results:', error);
            setTimeout(() => getProcessingResults(videoId), 5000);
         });
   }

   // Check if on the transcripts page and set up to load and display transcripts
   var fileList = document.getElementById('fileList');
   if (fileList) {
      loadAndDisplayVideoNames();
   }

   // Function to load and display video names
   function loadAndDisplayVideoNames() {
      const listContainer = document.getElementById('fileList');
      if (!listContainer) return; // Exit if fileList is not on this page

      fetch('/list_videos') // Assuming /list_videos returns a list of {name, id} pairs
         .then(response => response.json())
         .then(videos => {
            listContainer.innerHTML = ''; // Clear any existing content
            videos.forEach(video => {
               const link = document.createElement('a');
               link.href = '#';
               link.textContent = video.name;
               link.onclick = function (event) {
                  event.preventDefault(); // Prevent default anchor behavior
                  fetchCaptionsAndTransform(video.id); // Fetch captions when clicked
               };
               listContainer.appendChild(link);
               listContainer.appendChild(document.createElement('br'));
            });
         })
         .catch(error => {
            console.error('Error fetching video list:', error);
         });
   }

   // Function to fetch captions, store them, and call transformText
   function fetchCaptionsAndTransform(videoId) {
      fetch(`/get_captions/${videoId}`) // Assuming /get_captions/{videoId} endpoint returns captions
         .then(response => {
            if (!response.ok) throw new Error('Failed to fetch captions');
            return response.text();
         })
         .then(captions => {
            // Store captions in variable
            uploadedTextContent = captions;

            // Alert the captions for checking
            alert(`Captions for video ID ${videoId}: ${captions}`);

            // Log the captions to the console (optional, for debugging)
            console.log('Captions loaded for video ID:', videoId);

            // Call transformText with captions, mimicking the functionality of file upload
            transformText(uploadedTextContent);
         })
         .catch(error => {
            console.error('Error loading captions:', error);
            alert('Failed to load captions: ' + error.message);
         });
   }


   // Handles text file uploads
   document.getElementById('loadTextBtn').addEventListener('click', function () {
      var input = document.createElement('input');
      input.type = 'file';
      input.accept = 'text/*';  // Set the accepted file types to text.
      input.onchange = e => {
         var file = e.target.files[0];
         var reader = new FileReader();
         reader.onload = function (e) {
            uploadedTextContent = e.target.result; // Save the loaded text content.
            alert(file.name + " text uploaded successfully");
         };
         reader.readAsText(file);  // Read the file as text.
      };
      input.click();  // Trigger the file selection dialog.
   });

   // Handle transformation request
   document.getElementById('transformBtn').addEventListener('click', function () {
      if (!uploadedTextContent) {
         console.log('No file uploaded.');
         alert("Please upload a file first");
      } else {
         alert("Transformation started. Please wait for the download to begin.")
         transformText(uploadedTextContent);
      }
   });



   // Send the text to the server for translation
   async function transformText(textContent) {
      console.log('Sending POST request with text content:', textContent);
      try {
         const response = await fetch('/translate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ text: textContent }),
         });
         if (!response.ok) {
            throw new Error(`HTTP error during translation! Status: ${response.status}`);
         }
         const data = await response.json();
         console.log('Received translated text:', data.translated_text);
         saveTextAsFile(data.translated_text, "translated_output");
      } catch (error) {
         console.error('Error during text translation:', error);
      }
   }

   // Save the translated text as a downloadable file
   function saveTextAsFile(textToSave, filename) {
      const blob = new Blob([textToSave], { type: 'text/plain;charset=utf-8' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = filename + ".txt";  // Set the default file name for download.
      document.body.appendChild(a);
      a.click();  // Simulate a click on the link to trigger the download.
      document.body.removeChild(a);
      URL.revokeObjectURL(url);  // Clean up the URL object.
   }
});
