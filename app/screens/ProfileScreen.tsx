import React, { useContext, useState } from 'react';
import { View, Text, StyleSheet, TouchableOpacity, Image, TextInput, ScrollView, GestureResponderEvent } from 'react-native';
import { ProgressBar, Switch, Button } from 'react-native-paper';
import { UserContext } from '../context/UserContext';
import * as ImagePicker from 'expo-image-picker';

type ProfileScreenProps = {};

const ProfileScreen: React.FC<ProfileScreenProps> = () => {
  const { user, updateUser } = useContext(UserContext);
  const [isEditing, setIsEditing] = useState(false);
  const [tempUser, setTempUser] = useState({...user});
  
  const handleEditProfile = () => {
    if (isEditing) {
      updateUser(tempUser);
    }
    setIsEditing(!isEditing);
  };

  const pickImage = async (e: GestureResponderEvent) => {
    e.preventDefault();
    try {
      const result = await ImagePicker.launchImageLibraryAsync({
        mediaTypes: ImagePicker.MediaTypeOptions.Images,
        allowsEditing: true,
        aspect: [1, 1],
        quality: 1,
      });

      if (!result.canceled) {
        setTempUser({...tempUser, avatar: result.assets[0].uri});
      }
    } catch (error) {
      console.error('Error picking image:', error);
    }
  };

  return (
    <ScrollView style={styles.container}>
      {/* User Info Section */}
      <View style={styles.section}>
        <TouchableOpacity onPress={isEditing ? pickImage : undefined}>
          <Image 
            source={tempUser.avatar ? { uri: tempUser.avatar } : { uri: 'https://ui-avatars.com/api/?name=User&background=random' }} 
            style={styles.avatar} 
          />
          {isEditing && <Text style={styles.editHint}>Tap to change</Text>}
        </TouchableOpacity>
        
        {isEditing ? (
          <>
            <TextInput
              style={styles.input}
              value={tempUser.name}
              onChangeText={(text) => setTempUser({...tempUser, name: text})}
            />
            <TextInput
              style={styles.input}
              value={tempUser.email}
              onChangeText={(text) => setTempUser({...tempUser, email: text})}
              keyboardType="email-address"
            />
          </>
        ) : (
          <>
            <Text style={styles.name}>{user.name}</Text>
            <Text style={styles.email}>{user.email}</Text>
          </>
        )}
        
        <Button 
          mode="contained" 
          onPress={handleEditProfile}
          style={styles.button}
        >
          {isEditing ? 'Save Profile' : 'Edit Profile'}
        </Button>
      </View>

      {/* Usage Summary */}
      <View style={styles.section}>
        <Text style={styles.sectionTitle}>Usage Summary</Text>
        <Text>Tokens Used Today: {user.dailyUsage}/{user.dailyLimit}</Text>
        <ProgressBar progress={user.dailyUsage/user.dailyLimit} color="#4CAF50" />
        
        <Text>Monthly Usage: {user.monthlyUsage}/{user.monthlyLimit}</Text>
        <ProgressBar progress={user.monthlyUsage/user.monthlyLimit} color="#2196F3" />
        
        <Text>Next Reset: in {user.resetIn}</Text>
      </View>

      {/* Subscription Info */}
      <View style={styles.section}>
        <Text style={styles.sectionTitle}>Subscription</Text>
        <Text>Current Plan: {user.plan}</Text>
        <Text>Plan Benefits: Higher token limit, priority support</Text>
        <TouchableOpacity style={styles.button}>
          <Text style={styles.buttonText}>Upgrade Plan</Text>
        </TouchableOpacity>
      </View>

      {/* Token Wallet */}
      <View style={styles.section}>
        <Text style={styles.sectionTitle}>Token Wallet</Text>
        <Text>Current Balance: {user.tokens} tokens</Text>
        <TouchableOpacity style={styles.button}>
          <Text style={styles.buttonText}>Buy More Tokens</Text>
        </TouchableOpacity>
      </View>

      {/* Settings */}
      <View style={styles.section}>
        <Text style={styles.sectionTitle}>Settings</Text>
        <View style={styles.settingRow}>
          <Text>Dark Mode</Text>
          <Switch value={false} />
        </View>
        <TouchableOpacity style={styles.logoutButton}>
          <Text style={styles.logoutButtonText}>Logout</Text>
        </TouchableOpacity>
      </View>
    </ScrollView>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
    padding: 20,
    backgroundColor: '#f5f7fa',
  },
  section: {
    marginBottom: 20,
    padding: 20,
    backgroundColor: '#fff',
    borderRadius: 12,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.1,
    shadowRadius: 6,
    elevation: 3,
  },
  input: {
    borderWidth: 1,
    borderColor: '#ddd',
    borderRadius: 8,
    padding: 12,
    marginBottom: 15,
    fontSize: 16,
  },
  sectionTitle: {
    fontSize: 18,
    fontWeight: 'bold',
    marginBottom: 10,
  },
  avatar: {
    width: 100,
    height: 100,
    borderRadius: 50,
    alignSelf: 'center',
    marginBottom: 10,
  },
  name: {
    fontSize: 20,
    fontWeight: 'bold',
    textAlign: 'center',
    marginBottom: 5,
  },
  email: {
    textAlign: 'center',
    color: '#666',
    marginBottom: 15,
  },
  button: {
    backgroundColor: '#4CAF50',
    padding: 10,
    borderRadius: 5,
    alignItems: 'center',
    marginTop: 10,
  },
  buttonText: {
    color: 'white',
    fontWeight: 'bold',
  },
  logoutButton: {
    backgroundColor: '#f44336',
    padding: 10,
    borderRadius: 5,
    alignItems: 'center',
    marginTop: 20,
  },
  logoutButtonText: {
    color: 'white',
    fontWeight: 'bold',
  },
  settingRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginVertical: 8,
  },
  editHint: {
    fontSize: 12,
    color: '#666',
    textAlign: 'center',
  }
});

export default ProfileScreen;
