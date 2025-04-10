import { useState, useRef } from 'react';
import { StyleSheet, Text, View, TouchableOpacity, ActivityIndicator } from 'react-native';
import { CameraView, useCameraPermissions } from 'expo-camera';
import { MaterialIcons, Ionicons } from '@expo/vector-icons';
import { TextInput } from 'react-native';

type CameraType = 'back' | 'front';
type FlashMode = 'off' | 'on' | 'auto' | 'torch' | undefined;
type ChatMessage = {
  text: string;
  sender: 'user' | 'bot';
};

export default function ScanScreen() {
  const [facing, setFacing] = useState<CameraType>('back');
  const [flash, setFlash] = useState<FlashMode>('off');
  const [permission, requestPermission] = useCameraPermissions();
  const [isProcessing, setIsProcessing] = useState(false);
  const [detectedText, setDetectedText] = useState('');
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [inputText, setInputText] = useState('');
  const cameraRef = useRef<CameraView>(null);

  if (!permission) {
    return <View />;
  }

  if (!permission.granted) {
    return (
      <View style={styles.container}>
        <Text style={styles.message}>We need camera permission to scan math problems</Text>
        <TouchableOpacity style={styles.permissionButton} onPress={requestPermission}>
          <Text style={styles.permissionButtonText}>Grant Permission</Text>
        </TouchableOpacity>
      </View>
    );
  }

  const handleScan = async () => {
    if (!cameraRef.current) return;
    
    setIsProcessing(true);
    setDetectedText('Processing...');
    
    try {
      const photo = await cameraRef.current?.takePictureAsync({
        quality: 0.8,
        base64: true
      });

      if (!photo?.base64) {
        throw new Error('Failed to capture image');
      }

      const response = await fetch('http://localhost:8000/api/math-scan', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          image: photo.base64,
          timestamp: new Date().toISOString()
        })
      });

      if (!response.ok) throw new Error('API request failed');
      
      const { equation, solution } = await response.json();
      setDetectedText(`Equation: ${equation}\nSolution: ${solution}`);

    } catch (error) {
      console.error('Scan error:', error);
      setDetectedText(error instanceof Error ? error.message : 'Scan failed');
    } finally {
      setIsProcessing(false);
    }
  };

  const handleSendMessage = async () => {
    if (!inputText.trim()) return;
    
    setMessages(prev => [...prev, {text: inputText, sender: 'user'}]);
    setInputText('');
    
    try {
      console.log('Sending message to API:', inputText);
      const response = await fetch('http://localhost:8000/api/chat', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          message: inputText,
          context: detectedText
        })
      });

      console.log('API response status:', response.status);
      
      if (!response.ok) {
        const errorBody = await response.text();
        console.error('API error response:', errorBody);
        throw new Error(`API request failed: ${response.status}`);
      }
      
      const responseData = await response.json();
      console.log('API response data:', responseData);
      
      if (!responseData.response) {
        throw new Error('Invalid response format');
      }
      
      setMessages(prev => [...prev, {text: responseData.response, sender: 'bot'}]);
      
    } catch (error) {
      console.error('Full chat error:', error);
      setMessages(prev => [...prev, {text: `Error: ${error instanceof Error ? error.message : 'Unknown error'}`, sender: 'bot'}]);
    }
  };

  const toggleFlash = () => {
    setFlash(current => {
      switch(current) {
        case 'off': return 'torch';
        case 'torch': return 'off';
        default: return 'off';
      }
    });
  };

  const toggleCameraType = () => {
    setFacing(current => (current === 'back' ? 'front' : 'back'));
  };

  return (
    <View style={styles.container}>
      <CameraView 
        style={styles.camera}
        facing={facing}
        flash={flash}
        ref={cameraRef}
      >
        <View style={styles.controls}>
          <TouchableOpacity style={styles.controlButton} onPress={toggleFlash}>
            <Ionicons 
              name={flash === 'off' ? 'flash-off' : 'flash'} 
              size={28} 
              color="white" 
            />
          </TouchableOpacity>
          
          <TouchableOpacity style={styles.controlButton} onPress={toggleCameraType}>
            <Ionicons name="camera-reverse" size={28} color="white" />
          </TouchableOpacity>
        </View>

        <View style={styles.scanOverlay}>
          <View style={styles.scanFrame} />
          {!isProcessing ? (
            <TouchableOpacity style={styles.scanButton} onPress={handleScan}>
              <MaterialIcons name="document-scanner" size={40.0} color="white" />
            </TouchableOpacity>
          ) : (
            <TouchableOpacity style={styles.scanButton}>
              <ActivityIndicator size="large" color="white" />
            </TouchableOpacity>
          )}
        </View>
      </CameraView>

      {detectedText && (
        <View style={styles.resultContainer}>
          <Text style={styles.resultText}>{detectedText}</Text>
        </View>
      )}

      <View style={styles.chatContainer}>
        {messages.map((message, index) => (
          <View key={index} style={[styles.messageBubble, message.sender === 'user' ? styles.userBubble : styles.botBubble]}>
            <Text style={styles.messageText}>{message.text}</Text>
          </View>
        ))}
        <View style={styles.inputContainer}>
          <TextInput 
            style={styles.input} 
            value={inputText} 
            onChangeText={setInputText} 
            placeholder="Type a message"
          />
          <TouchableOpacity style={styles.sendButton} onPress={handleSendMessage}>
            <Text style={styles.messageText}>Send</Text>
          </TouchableOpacity>
        </View>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
  },
  camera: {
    flex: 1,
  },
  controls: {
    position: 'absolute',
    top: 20,
    right: 20,
    flexDirection: 'column',
    gap: 15,
  },
  controlButton: {
    backgroundColor: 'rgba(0,0,0,0.5)',
    padding: 10,
    borderRadius: 50,
  },
  scanOverlay: {
    position: 'absolute',
    bottom: 100,
    left: 0,
    right: 0,
    alignItems: 'center',
  },
  scanFrame: {
    width: 200,
    height: 200,
    borderWidth: 2,
    borderColor: 'white',
    marginBottom: 20,
  },
  scanButton: {
    backgroundColor: 'rgba(0,0,0,0.7)',
    padding: 15,
    borderRadius: 50,
  },
  resultContainer: {
    position: 'absolute',
    bottom: 100,
    left: 20,
    right: 20,
    backgroundColor: 'rgba(0,0,0,0.7)',
    padding: 15,
    borderRadius: 10,
  },
  resultText: {
    color: 'white',
    fontSize: 18,
    textAlign: 'center',
  },
  message: {
    flex: 1,
    textAlign: 'center',
    textAlignVertical: 'center',
    color: 'white',
    fontSize: 18,
    backgroundColor: '#000',
  },
  permissionButton: {
    backgroundColor: '#4CAF50',
    borderRadius: 10,
    padding: 15,
    elevation: 5,
  },
  permissionButtonText: {
    color: 'white',
    fontSize: 18,
    textAlign: 'center',
  },
  chatContainer: {
    position: 'absolute',
    bottom: 0,
    left: 0,
    right: 0,
    height: '40%',
    backgroundColor: 'rgba(0,0,0,0.8)',
    padding: 10,
  },
  messageBubble: {
    padding: 10,
    borderRadius: 10,
    marginVertical: 5,
    maxWidth: '80%',
  },
  userBubble: {
    alignSelf: 'flex-end',
    backgroundColor: '#4CAF50',
  },
  botBubble: {
    alignSelf: 'flex-start',
    backgroundColor: '#333',
  },
  messageText: {
    color: 'white',
  },
  inputContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    marginTop: 10,
  },
  input: {
    flex: 1,
    backgroundColor: 'white',
    borderRadius: 20,
    padding: 10,
    marginRight: 10,
  },
  sendButton: {
    backgroundColor: '#4CAF50',
    borderRadius: 20,
    padding: 10,
  }
});
