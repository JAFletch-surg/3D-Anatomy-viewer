document.addEventListener('DOMContentLoaded', function() {
    // Canvas and Three.js variables
    const canvas = document.getElementById('viewer');
    let camera, scene, renderer, controls;
    let model;
    let modelNodes = {};
    let isWireframeMode = false;
    let frameCount = 0;
    let lastTime = performance.now();

    // UI State Management
    let isControlsCollapsed = false;
    let isMobileControlsOpen = false;
    let originalCameraPosition = new THREE.Vector3(0.5, 0.5, 0.5);
    let originalCameraTarget = new THREE.Vector3(0, 0, 0);

    // Performance monitoring
    let renderStats = {
        fps: 0,
        polygons: 0,
        vertices: 0
    };

    // Initialize the 3D viewer
    init();
    animate();

    function init() {
        try {
            // Scene setup
            scene = new THREE.Scene();
            scene.background = new THREE.Color(0x000000);

            // Camera setup
            camera = new THREE.PerspectiveCamera(60, window.innerWidth / window.innerHeight, 0.1, 1000);
            camera.position.copy(originalCameraPosition);

            // Renderer setup - MEDICAL VISUALIZATION
            renderer = new THREE.WebGLRenderer({
                canvas: canvas,
                antialias: true,
                preserveDrawingBuffer: true,
                alpha: false,
                powerPreference: "high-performance"
            });
            
            renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
            renderer.setSize(window.innerWidth, window.innerHeight);
            renderer.shadowMap.enabled = true;
            renderer.shadowMap.type = THREE.PCFSoftShadowMap;
            
            // MEDICAL RENDERER SETTINGS - Clean color reproduction
            renderer.outputEncoding = THREE.sRGBEncoding;
            renderer.toneMapping = THREE.LinearToneMapping; // No color distortion
            renderer.toneMappingExposure = 1.0; // No exposure adjustment

            // OrbitControls setup
            controls = new THREE.OrbitControls(camera, renderer.domElement);
            controls.enableDamping = true;
            controls.dampingFactor = 0.05;
            controls.screenSpacePanning = true;
            controls.minDistance = 0.1;
            controls.maxDistance = 5;
            controls.maxPolarAngle = Math.PI;
            controls.target.copy(originalCameraTarget);

            // Medical lighting setup
            setupLights();

            // Load model
            loadModel();

            // Setup event listeners
            setupEventListeners();

            // Initialize UI
            initializeUI();

            console.log('Medical 3D Viewer initialized successfully');
            
        } catch (error) {
            console.error('Failed to initialize 3D viewer:', error);
            showErrorMessage('Failed to initialize 3D viewer. Please check WebGL support.');
        }
    }

    function setupLights() {
        // Remove any existing lights
        scene.children = scene.children.filter(child => !(child instanceof THREE.Light));

        // MEDICAL LIGHTING SETUP - Clean, even illumination
        setupMedicalLighting();
    }

    function setupMedicalLighting() {
        console.log('Setting up clean medical lighting...');
        
        // === PRIMARY KEY LIGHT ===
        // Main light source - bright, from upper right
        const keyLight = new THREE.DirectionalLight(0xffffff, 0.7);
        keyLight.position.set(10, 12, 8);
        keyLight.castShadow = true;
        
        // Configure shadows for clean edges
        keyLight.shadow.mapSize.width = 4048;
        keyLight.shadow.mapSize.height = 4048;
        keyLight.shadow.camera.near = 0.5;
        keyLight.shadow.camera.far = 50;
        keyLight.shadow.camera.left = -10;
        keyLight.shadow.camera.right = 10;
        keyLight.shadow.camera.top = 10;
        keyLight.shadow.camera.bottom = -10;
        keyLight.shadow.bias = -0.005;
        keyLight.shadow.normalBias = 0.02;
        scene.add(keyLight);

        // === FILL LIGHT ===
        // Softer light from opposite side to reduce harsh shadows
        const fillLight = new THREE.DirectionalLight(0xe8f4fd, 0.4);
        fillLight.position.set(-8, 6, 5);
        scene.add(fillLight);

        // === RIM/EDGE LIGHT ===
        // Creates definition and separation from background
        const rimLight = new THREE.DirectionalLight(0xfff8f0, 0.7);
        rimLight.position.set(2, 8, -12);
        scene.add(rimLight);

        // === BOTTOM FILL LIGHT ===
        // Prevents dark undersides, important for medical visualization
        const bottomLight = new THREE.DirectionalLight(0xf0f8ff, 0.03);
        bottomLight.position.set(0, -8, 3);
        scene.add(bottomLight);

        // === AMBIENT LIGHT ===
        // Overall base illumination for even lighting
        const ambientLight = new THREE.AmbientLight(0xf5f8ff, 0.3);
        scene.add(ambientLight);

        // === SUPPLEMENTAL SIDE LIGHTS ===
        // Additional lighting for complete coverage
        const sideLight1 = new THREE.DirectionalLight(0xffffff, 0.5);
        sideLight1.position.set(15, 0, 0);
        scene.add(sideLight1);

        const sideLight2 = new THREE.DirectionalLight(0xffffff, 0.2);
        sideLight2.position.set(-15, 0, 0);
        scene.add(sideLight2);

        console.log('Medical lighting setup complete - 7 lights configured');
    }

    function loadModel() {
        if (!modelFilename) {
            showErrorMessage('No model filename provided');
            return;
        }

        const loader = new THREE.GLTFLoader();
        
        // Add loading manager for better progress tracking
        const loadingManager = new THREE.LoadingManager();
        loader.manager = loadingManager;

        loadingManager.onLoad = function() {
            console.log('Model loading completed');
        };

        loadingManager.onError = function(error) {
            console.error('Loading manager error:', error);
            showErrorMessage('Failed to load model resources');
        };

        loader.load(
            `/static/uploads/${modelFilename}`,
            function(gltf) {
                try {
                    handleModelLoaded(gltf);
                } catch (error) {
                    console.error('Error processing loaded model:', error);
                    showErrorMessage('Error processing 3D model');
                }
            },
            function(xhr) {
                if (xhr.lengthComputable) {
                    const percent = (xhr.loaded / xhr.total * 100).toFixed(1);
                    updateLoadingProgress(percent);
                    console.log(`Loading progress: ${percent}%`);
                }
            },
            function(error) {
                console.error('Error loading model:', error);
                showErrorMessage('Failed to load 3D model. Please check the file format.');
            }
        );
    }

    function handleModelLoaded(gltf) {
        model = gltf.scene;
        let totalPolygons = 0;
        let totalVertices = 0;

        // Process each mesh in the model
        model.traverse(function(node) {
            if (node.isMesh) {
                // Store node reference
                modelNodes[node.name] = node;
                
                // Calculate statistics
                if (node.geometry) {
                    const positions = node.geometry.attributes.position;
                    if (positions) {
                        totalVertices += positions.count;
                        totalPolygons += positions.count / 3;
                    }
                }

                // Improve geometry
                if (node.geometry) {
                    node.geometry.computeVertexNormals();
                    node.geometry.computeBoundingBox();
                    node.geometry.computeBoundingSphere();
                }

                // Dispose old material
                if (node.material) {
                    node.material.dispose();
                }

                // Enhanced material for medical visualization
                const materialColor = getMaterialColor(node.name);
                node.material = new THREE.MeshStandardMaterial({
                    color: materialColor,
                    roughness: 0.2,        // Slightly glossy for clean appearance
                    metalness: 0.0,         // Non-metallic (biological tissue)
                    transparent: true,      // Always enable transparency
                    opacity: 1.0,
                    side: THREE.DoubleSide,
                    flatShading: false,
                    alphaTest: 0.001,       // Small alpha test to improve performance
                    depthWrite: true,       // Keep depth writing for proper rendering
                    
                    // Subtle self-illumination for medical visibility
                    emissive: materialColor.clone().multiplyScalar(0.08),
                    emissiveIntensity: 0.0,
                    
                    // No environment reflections for clean look
                    envMapIntensity: 0.0
                });

                // Enable shadows
                node.castShadow = true;
                node.receiveShadow = true;

                // Add to userData for easy access
                node.userData.originalColor = materialColor.clone();
                node.userData.originalOpacity = 1.0;
            }
        });

        // Center and scale the model
        centerAndScaleModel(model);

        // Add model to scene
        scene.add(model);

        // Update statistics
        renderStats.polygons = Math.round(totalPolygons);
        renderStats.vertices = totalVertices;

        // Update UI
        updateModelInfo(Math.round(totalPolygons));
        hideLoadingOverlay();

        // Set initial camera position
        resetCameraView();

        console.log(`Model loaded: ${totalVertices} vertices, ${Math.round(totalPolygons)} polygons`);
    }

    function getMaterialColor(nodeName) {
        // MEDICAL COLORS - keeping original color scheme
        const colorMap = {
            'label_1': new THREE.Color(0xCB0404), // Artery - Crimson Red
            'label_2': new THREE.Color(0x0065F8), // Vein - Royal Blue  
            'label_3': new THREE.Color(0xF14C4C), // Duodenum - Deep Pink
            'label_4': new THREE.Color(0xff29ca3), // Colon - Peru
            'label_5': new THREE.Color(0xFFB22C), // Pancreas - Peach
            'label_6': new THREE.Color(0x38E54D)  // Tumor - Lime Green
        };

        return colorMap[nodeName] || new THREE.Color(0.8, 0.8, 0.8); // Default light gray
    }

    function centerAndScaleModel(model) {
        // Calculate bounding box
        const box = new THREE.Box3().setFromObject(model);
        const center = box.getCenter(new THREE.Vector3());
        const size = box.getSize(new THREE.Vector3());

        // Center the model
        model.position.sub(center);

        // Scale the model to fit in viewport
        const maxDim = Math.max(size.x, size.y, size.z);
        const scale = 1.5 / maxDim; // Make it slightly smaller than viewport
        model.scale.multiplyScalar(scale);

        // Update original camera position based on model size
        const distance = maxDim * 0.8;
        originalCameraPosition.set(distance, distance, distance);
        originalCameraTarget.set(0, 0, 0);
    }

    function setupEventListeners() {
        // Window resize
        window.addEventListener('resize', onWindowResize, false);

        // Prevent context menu on right click
        if (renderer && renderer.domElement) {
            renderer.domElement.addEventListener('contextmenu', function(event) {
                event.preventDefault();
            });
        }

        // Keyboard shortcuts
        document.addEventListener('keydown', function(event) {
            switch(event.code) {
                case 'Space':
                    event.preventDefault();
                    resetCameraView();
                    break;
                case 'KeyW':
                    if (event.ctrlKey || event.metaKey) {
                        event.preventDefault();
                        toggleWireframe();
                    }
                    break;
                case 'KeyS':
                    if (event.ctrlKey || event.metaKey) {
                        event.preventDefault();
                        takeScreenshot();
                    }
                    break;
                case 'KeyF':
                    if (event.ctrlKey || event.metaKey) {
                        event.preventDefault();
                        toggleFullscreen();
                    }
                    break;
            }
        });
    }

    // ===== UI INITIALIZATION =====

    function initializeUI() {
        // Desktop controls collapse/expand
        const collapseBtn = document.getElementById('collapse-btn');
        const controlsContainer = document.getElementById('controls-container');
        
        if (collapseBtn && controlsContainer) {
            collapseBtn.addEventListener('click', function() {
                isControlsCollapsed = !isControlsCollapsed;
                controlsContainer.style.display = isControlsCollapsed ? 'none' : 'block';
                const svg = collapseBtn.querySelector('svg');
                if (svg) {
                    svg.style.transform = isControlsCollapsed ? 'rotate(180deg)' : 'rotate(0deg)';
                }
            });
        }
        
        // Mobile controls
        const mobileBtn = document.getElementById('mobile-controls-btn');
        const mobileControls = document.getElementById('mobile-controls');
        const closeMobileBtn = document.getElementById('close-mobile');
        
        if (mobileBtn && mobileControls) {
            mobileBtn.addEventListener('click', function() {
                isMobileControlsOpen = !isMobileControlsOpen;
                mobileControls.style.transform = isMobileControlsOpen ? 'translateY(0)' : 'translateY(100%)';
            });
        }
        
        if (closeMobileBtn && mobileControls) {
            closeMobileBtn.addEventListener('click', function() {
                isMobileControlsOpen = false;
                mobileControls.style.transform = 'translateY(100%)';
            });
        }
        
        // Visibility toggles
        setupVisibilityToggles();
        
        // Toolbar buttons
        setupToolbarButtons();
        
        // Quick actions
        setupQuickActions();
        
        // Opacity sliders
        setupOpacitySliders();
    }

    function setupVisibilityToggles() {
        // Desktop visibility toggles
        document.querySelectorAll('.visibility-toggle').forEach(button => {
            button.addEventListener('click', function() {
                const label = this.getAttribute('data-label');
                toggleVisibility(label, this);
            });
        });
        
        // Mobile visibility toggles
        document.querySelectorAll('.visibility-toggle-mobile').forEach(button => {
            button.addEventListener('click', function() {
                const label = this.getAttribute('data-label');
                toggleVisibility(label, this);
            });
        });
    }

    function setupToolbarButtons() {
        // Reset view
        const resetBtn = document.getElementById('reset-view');
        if (resetBtn) {
            resetBtn.addEventListener('click', function() {
                resetCameraView();
                showToast('View reset to default position');
            });
        }
        
        // Screenshot
        const screenshotBtn = document.getElementById('screenshot-btn');
        if (screenshotBtn) {
            screenshotBtn.addEventListener('click', function() {
                takeScreenshot();
            });
        }
        
        // Fullscreen
        const fullscreenBtn = document.getElementById('fullscreen-btn');
        if (fullscreenBtn) {
            fullscreenBtn.addEventListener('click', function() {
                toggleFullscreen();
            });
        }
        
        // Wireframe
        const wireframeBtn = document.getElementById('wireframe-btn');
        if (wireframeBtn) {
            wireframeBtn.addEventListener('click', function() {
                toggleWireframe();
            });
        }
        
        // Retry button
        const retryBtn = document.getElementById('retry-btn');
        if (retryBtn) {
            retryBtn.addEventListener('click', function() {
                location.reload();
            });
        }
    }

    function setupQuickActions() {
        const showAllBtn = document.getElementById('show-all');
        const hideAllBtn = document.getElementById('hide-all');
        
        if (showAllBtn) {
            showAllBtn.addEventListener('click', function() {
                showAllParts();
                showToast('All anatomy parts shown');
            });
        }
        
        if (hideAllBtn) {
            hideAllBtn.addEventListener('click', function() {
                hideAllParts();
                showToast('All anatomy parts hidden');
            });
        }
    }

    function setupOpacitySliders() {
        // FIXED: Proper event listener setup for opacity sliders
        console.log('Setting up opacity sliders...');
        
        document.querySelectorAll('.slider').forEach((slider, index) => {
            console.log(`Found slider ${index}: data-label="${slider.getAttribute('data-label')}"`);
            
            // Find the associated opacity value display
            const controlItem = slider.closest('.control-item');
            const opacityValue = controlItem ? controlItem.querySelector('.opacity-value') : null;
            
            slider.addEventListener('input', function(e) {
                const label = this.getAttribute('data-label');
                const opacity = parseFloat(this.value) / 100.0;
                console.log(`Slider input: ${label} -> ${opacity}`);
                setPartOpacity(label, opacity);
                
                // Update the visual feedback
                updateSliderVisualFeedback(this, opacity);
                
                // Update the percentage display
                if (opacityValue) {
                    opacityValue.textContent = `${Math.round(opacity * 100)}%`;
                }
            });
            
            // Also handle change event for better compatibility
            slider.addEventListener('change', function(e) {
                const label = this.getAttribute('data-label');
                const opacity = parseFloat(this.value) / 100.0;
                console.log(`Slider change: ${label} -> ${opacity}`);
                setPartOpacity(label, opacity);
                
                // Update the percentage display
                if (opacityValue) {
                    opacityValue.textContent = `${Math.round(opacity * 100)}%`;
                }
            });
        });
    }

    function updateSliderVisualFeedback(slider, opacity) {
        // Visual feedback for the slider
        const percentage = Math.round(opacity * 100);
        slider.style.background = `linear-gradient(to right, #0ea5e9 0%, #0ea5e9 ${percentage}%, rgba(255,255,255,0.2) ${percentage}%, rgba(255,255,255,0.2) 100%)`;
    }

    // ===== 3D VIEWER FUNCTIONS =====

    function toggleVisibility(label, buttonElement) {
        const node = modelNodes[label];
        
        if (node) {
            node.visible = !node.visible;
            
            // Update all buttons with the same label (desktop and mobile)
            const allButtons = document.querySelectorAll(`[data-label="${label}"]`);
            allButtons.forEach(btn => {
                if (btn.classList.contains('visibility-toggle') || btn.classList.contains('visibility-toggle-mobile')) {
                    const useElement = btn.querySelector('use');
                    if (useElement) {
                        if (node.visible) {
                            btn.classList.remove('hidden-part');
                            useElement.setAttribute('href', '#eye-open');
                        } else {
                            btn.classList.add('hidden-part');
                            useElement.setAttribute('href', '#eye-closed');
                        }
                    }
                }
            });
            
            console.log(`${label} visibility: ${node.visible}`);
        }
    }

    function setPartOpacity(label, opacity) {
        console.log(`setPartOpacity called: ${label} -> ${opacity}`);
        const node = modelNodes[label];
        
        if (node && node.material) {
            console.log(`Found node for ${label}, setting opacity...`);
            // FIXED: Proper opacity handling
            const clampedOpacity = Math.max(0.01, Math.min(1.0, opacity)); // Clamp between 0.01 and 1.0
            node.material.opacity = clampedOpacity;
            node.material.transparent = clampedOpacity < 1.0;
            node.material.needsUpdate = true;
            
            // Handle depth sorting for transparent objects
            if (clampedOpacity < 1.0) {
                node.material.depthWrite = false;
                node.renderOrder = 1000 + Math.round((1 - clampedOpacity) * 100); // Higher values render later
            } else {
                node.material.depthWrite = true;
                node.renderOrder = 0;
            }
            
            console.log(`${label} opacity set to: ${clampedOpacity}, transparent: ${node.material.transparent}`);
        } else {
            console.log(`Node not found for label: ${label}. Available nodes:`, Object.keys(modelNodes));
        }
    }

    function showAllParts() {
        Object.values(modelNodes).forEach(node => {
            node.visible = true;
        });
        
        // Update UI
        document.querySelectorAll('.visibility-toggle, .visibility-toggle-mobile').forEach(btn => {
            btn.classList.remove('hidden-part');
            const useElement = btn.querySelector('use');
            if (useElement) {
                useElement.setAttribute('href', '#eye-open');
            }
        });
        
        // Reset opacity sliders and value displays
        document.querySelectorAll('.slider').forEach(slider => {
            slider.value = 100;
            const label = slider.getAttribute('data-label');
            setPartOpacity(label, 1);
            updateSliderVisualFeedback(slider, 1);
            
            // Update percentage display
            const controlItem = slider.closest('.control-item');
            const opacityValue = controlItem ? controlItem.querySelector('.opacity-value') : null;
            if (opacityValue) {
                opacityValue.textContent = '100%';
            }
        });
    }

    function hideAllParts() {
        Object.values(modelNodes).forEach(node => {
            node.visible = false;
        });
        
        // Update UI
        document.querySelectorAll('.visibility-toggle, .visibility-toggle-mobile').forEach(btn => {
            btn.classList.add('hidden-part');
            const useElement = btn.querySelector('use');
            if (useElement) {
                useElement.setAttribute('href', '#eye-closed');
            }
        });
    }

    function resetCameraView() {
        if (controls && camera) {
            // Animate camera to original position
            animateCameraTo(originalCameraPosition, originalCameraTarget, 1000);
        }
    }

    function animateCameraTo(targetPosition, targetLookAt, duration = 1000) {
        const startPosition = camera.position.clone();
        const startTarget = controls.target.clone();
        const startTime = performance.now();

        function animate() {
            const elapsed = performance.now() - startTime;
            const progress = Math.min(elapsed / duration, 1);
            
            // Smooth easing function
            const easeProgress = 1 - Math.pow(1 - progress, 3);
            
            // Interpolate position
            camera.position.lerpVectors(startPosition, targetPosition, easeProgress);
            
            // Interpolate target
            controls.target.lerpVectors(startTarget, targetLookAt, easeProgress);
            
            controls.update();
            
            if (progress < 1) {
                requestAnimationFrame(animate);
            }
        }
        
        animate();
    }

    function takeScreenshot() {
        if (renderer) {
            try {
                // Ensure we're rendering the current frame
                renderer.render(scene, camera);
                
                // Create download link
                const link = document.createElement('a');
                const timestamp = new Date().toISOString().slice(0, 19).replace(/:/g, '-');
                link.download = `anatomy-model-${timestamp}.png`;
                link.href = renderer.domElement.toDataURL('image/png');
                link.click();
                
                showToast('Screenshot saved successfully');
                console.log('Screenshot taken');
            } catch (error) {
                console.error('Screenshot failed:', error);
                showToast('Screenshot failed', 'error');
            }
        }
    }

    function toggleFullscreen() {
        try {
            if (!document.fullscreenElement) {
                document.documentElement.requestFullscreen().then(() => {
                    showToast('Entered fullscreen mode');
                }).catch(() => {
                    showToast('Fullscreen not supported', 'error');
                });
            } else {
                document.exitFullscreen().then(() => {
                    showToast('Exited fullscreen mode');
                });
            }
        } catch (error) {
            console.error('Fullscreen toggle failed:', error);
            showToast('Fullscreen operation failed', 'error');
        }
    }

    function toggleWireframe() {
        isWireframeMode = !isWireframeMode;
        
        Object.values(modelNodes).forEach(node => {
            if (node.material) {
                node.material.wireframe = isWireframeMode;
                node.material.needsUpdate = true;
            }
        });
        
        const message = isWireframeMode ? 'Wireframe mode enabled' : 'Wireframe mode disabled';
        showToast(message);
        console.log(message);
    }

    // ===== UI UTILITY FUNCTIONS =====

    function hideLoadingOverlay() {
        const loadingOverlay = document.getElementById('loading-overlay');
        if (loadingOverlay) {
            loadingOverlay.style.opacity = '0';
            setTimeout(() => {
                loadingOverlay.style.display = 'none';
            }, 300);
        }
    }

    function showErrorMessage(message = 'An error occurred') {
        const loadingOverlay = document.getElementById('loading-overlay');
        const errorMessage = document.getElementById('error-message');
        
        if (loadingOverlay) loadingOverlay.style.display = 'none';
        if (errorMessage) errorMessage.classList.remove('hidden');
        
        // Use global error handler if available
        if (window.showError) {
            window.showError(message);
        }
        
        console.error('Viewer error:', message);
    }

    function updateLoadingProgress(percent) {
        const loadingOverlay = document.getElementById('loading-overlay');
        if (loadingOverlay) {
            const progressText = loadingOverlay.querySelector('.text-white.font-medium');
            if (progressText) {
                progressText.textContent = `Loading Model ${percent}%`;
            }
        }
    }

    function updateModelInfo(polyCount) {
        const modelNameElem = document.getElementById('model-name');
        const polyCountElem = document.getElementById('poly-count');
        
        if (modelNameElem) {
            modelNameElem.textContent = modelFilename || 'Anatomy Model';
        }
        
        if (polyCountElem) {
            polyCountElem.textContent = polyCount.toLocaleString();
        }
    }

    function showToast(message, type = 'success') {
        // Use global notification system if available
        if (type === 'success' && window.showSuccess) {
            window.showSuccess(message);
        } else if (type === 'error' && window.showError) {
            window.showError(message);
        } else {
            // Fallback toast implementation
            const toast = document.createElement('div');
            toast.className = `fixed top-4 left-1/2 transform -translate-x-1/2 px-4 py-2 rounded-lg z-50 transition-opacity text-white ${
                type === 'error' ? 'bg-red-500' : 'bg-green-500'
            }`;
            toast.textContent = message;
            
            document.body.appendChild(toast);
            
            setTimeout(() => {
                toast.style.opacity = '0';
                setTimeout(() => {
                    if (document.body.contains(toast)) {
                        document.body.removeChild(toast);
                    }
                }, 300);
            }, 2000);
        }
    }

    // ===== PERFORMANCE MONITORING =====

    function updateFPS() {
        frameCount++;
        const currentTime = performance.now();
        
        if (currentTime - lastTime >= 1000) {
            const fps = Math.round((frameCount * 1000) / (currentTime - lastTime));
            const fpsCounter = document.getElementById('fps-counter');
            if (fpsCounter) {
                fpsCounter.textContent = fps;
            }
            renderStats.fps = fps;
            frameCount = 0;
            lastTime = currentTime;
        }
    }

    function onWindowResize() {
        if (camera && renderer) {
            const newWidth = window.innerWidth;
            const newHeight = window.innerHeight;
            
            camera.aspect = newWidth / newHeight;
            camera.updateProjectionMatrix();
            renderer.setSize(newWidth, newHeight);
            
            console.log(`Viewport resized to ${newWidth}x${newHeight}`);
        }
    }

    // ===== ANIMATION LOOP =====

    function animate() {
        requestAnimationFrame(animate);
        
        // Update FPS counter
        updateFPS();
        
        // Update controls
        if (controls) {
            controls.update();
        }
        
        // IMPROVED: Sort transparent objects for better rendering
        if (scene && scene.children.length > 0) {
            scene.traverse(function(object) {
                if (object.isMesh && object.material && object.material.transparent && object.material.opacity < 1) {
                    // Calculate distance to camera for depth sorting
                    const distance = camera.position.distanceTo(object.position);
                    object.renderOrder = Math.round(distance * 1000);
                }
            });
        }
        
        // Render the scene
        if (renderer && scene && camera) {
            renderer.render(scene, camera);
        }
    }

    // ===== CLEANUP =====

    // Cleanup function for memory management
    window.addEventListener('beforeunload', function() {
        if (renderer) {
            renderer.dispose();
        }
        
        // Dispose geometries and materials
        if (scene) {
            scene.traverse(function(object) {
                if (object.geometry) {
                    object.geometry.dispose();
                }
                if (object.material) {
                    if (Array.isArray(object.material)) {
                        object.material.forEach(material => material.dispose());
                    } else {
                        object.material.dispose();
                    }
                }
            });
        }
        
        console.log('3D viewer resources cleaned up');
    });

    // Export some functions for external access
    window.viewer3D = {
        resetCamera: resetCameraView,
        takeScreenshot: takeScreenshot,
        toggleWireframe: toggleWireframe,
        showAllParts: showAllParts,
        hideAllParts: hideAllParts,
        getStats: () => renderStats,
        setPartOpacity: setPartOpacity
    };

    console.log('Medical 3D Viewer script loaded successfully');
});