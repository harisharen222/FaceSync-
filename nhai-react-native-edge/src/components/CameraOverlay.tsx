import React, { useEffect, useRef } from 'react';
import { View, StyleSheet, Animated, Text, Dimensions } from 'react-native';

interface CameraOverlayProps {
  isScanning: boolean;
  promptText: string;
  livenessSuccess: boolean;
}

const { width, height } = Dimensions.get('window');
const MASK_SIZE = 280;

/**
 * A highly polished, premium camera overlay with a central cutout for the face
 * and dynamic animated scanning effects. Uses subtle glassmorphism techniques.
 */
export const CameraOverlay: React.FC<CameraOverlayProps> = ({ 
  isScanning, 
  promptText, 
  livenessSuccess 
}) => {
  const scanAnim = useRef(new Animated.Value(0)).current;
  const successAnim = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    if (isScanning && !livenessSuccess) {
      Animated.loop(
        Animated.sequence([
          Animated.timing(scanAnim, {
            toValue: 1,
            duration: 1500,
            useNativeDriver: true,
          }),
          Animated.timing(scanAnim, {
            toValue: 0,
            duration: 1500,
            useNativeDriver: true,
          }),
        ])
      ).start();
    } else {
      scanAnim.stopAnimation();
    }

    if (livenessSuccess) {
      Animated.spring(successAnim, {
        toValue: 1,
        friction: 4,
        tension: 40,
        useNativeDriver: true,
      }).start();
    } else {
      successAnim.setValue(0);
    }
  }, [isScanning, livenessSuccess]);

  const translateY = scanAnim.interpolate({
    inputRange: [0, 1],
    outputRange: [-MASK_SIZE / 2 + 10, MASK_SIZE / 2 - 10],
  });

  const borderColor = successAnim.interpolate({
    inputRange: [0, 1],
    outputRange: ['rgba(255, 255, 255, 0.4)', 'rgba(76, 217, 100, 1)'],
  });

  return (
    <View style={StyleSheet.absoluteFill}>
      {/* Dimmed Background with transparent cutout */}
      <View style={styles.overlayContainer}>
        <View style={styles.maskContainer}>
          <Animated.View style={[styles.cutout, { borderColor, borderWidth: livenessSuccess ? 4 : 2 }]}>
            
            {/* Animated Scanning Line */}
            {isScanning && !livenessSuccess && (
              <Animated.View 
                style={[
                  styles.scanLine, 
                  { transform: [{ translateY }] }
                ]} 
              />
            )}

          </Animated.View>
        </View>
      </View>

      {/* Modern Prompt Card */}
      <View style={styles.promptWrapper}>
        <View style={styles.promptCard}>
          <Text style={styles.promptText}>{promptText}</Text>
        </View>
      </View>

    </View>
  );
};

const styles = StyleSheet.create({
  overlayContainer: {
    flex: 1,
    backgroundColor: 'rgba(0, 0, 0, 0.65)',
    justifyContent: 'center',
    alignItems: 'center',
  },
  maskContainer: {
    width: width,
    height: height,
    justifyContent: 'center',
    alignItems: 'center',
  },
  cutout: {
    width: MASK_SIZE,
    height: MASK_SIZE * 1.3,
    borderRadius: 200,
    backgroundColor: 'transparent',
    overflow: 'hidden',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 0 },
    shadowOpacity: 0.5,
    shadowRadius: 20,
    elevation: 10,
    // Note: To make the background strictly transparent while the rest is dark,
    // in a real app you would use react-native-svg or a specialized masked view.
    // For this prototype, we rely on the aesthetic border.
  },
  scanLine: {
    width: '100%',
    height: 3,
    backgroundColor: 'rgba(0, 255, 255, 0.8)',
    shadowColor: '#00FFFF',
    shadowOffset: { width: 0, height: 0 },
    shadowOpacity: 1,
    shadowRadius: 10,
    elevation: 5,
  },
  promptWrapper: {
    position: 'absolute',
    bottom: 100,
    width: '100%',
    alignItems: 'center',
  },
  promptCard: {
    backgroundColor: 'rgba(255, 255, 255, 0.15)',
    paddingVertical: 16,
    paddingHorizontal: 32,
    borderRadius: 30,
    borderWidth: 1,
    borderColor: 'rgba(255, 255, 255, 0.3)',
    // Glassmorphism effect via backdrop filter requires specific native modules,
    // so we approximate it with semi-transparent colors.
  },
  promptText: {
    color: '#FFFFFF',
    fontSize: 18,
    fontWeight: '600',
    letterSpacing: 0.5,
  }
});
