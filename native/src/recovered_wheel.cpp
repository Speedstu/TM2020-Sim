#include "tm2020/recovered_wheel.hpp"
#include <cmath>
#include <stdexcept>
namespace tm2020::recovered {
namespace {
void require(bool b,const char* why){if(!b)throw std::invalid_argument(why);}
void scalar(float x){require(std::isfinite(x)&&std::abs(x)<=1e6f,"Wheel kinematics exceeds finite domain");}
template<std::size_t N>void bounded(const std::array<float,N>& a){for(float x:a)scalar(x);}
void validate(const WheelKinematicState& s){bounded(std::array{s.length,s.speed,s.pending_compression,s.spin_rate_1c,s.phase_78,s.angle_7c,s.target_angle_80});bounded(s.normal_44);}
float curve(const VehicleCurveView& c,float x){return evaluate_curve(c.points,x,c.flags);}
}
void update_wheel_kinematics(WheelKinematicState& state,MeshTransform& wheel_pose,const WheelKinematicInput& input,
    const WheelKinematicParameters& p,std::span<const WheelSteeringMaterial> materials,float dt){
    validate(state);bounded(wheel_pose.rotation);bounded(wheel_pose.translation);bounded(input.model_local_point);
    bounded(std::array{input.steering_1430,input.blend_1c3c,input.blend_1c44,input.speed_parameter,p.rest_length_244,p.pose_offset_250,p.relaxation_258,p.reference_cd4,p.angle_limit_118c,p.angle_rate_1190});
    require(std::isfinite(dt)&&dt>0&&dt<=1,"Invalid wheel kinematic interval");require(materials.size()<=256,"Too many wheel materials");
    auto s=state;auto pose=wheel_pose;constexpr float period=1608.4954833984375f;
    float phase=dt*s.spin_rate_1c+s.phase_78;
    if(phase<0||phase>=period){phase=std::fmod(phase-0.f,period-0.f);if(phase<0)phase=phase+period;phase=phase+0.f;}s.phase_78=phase;
    const auto n=s.normal_44;const float squared=(n[0]*n[0]+n[1]*n[1])+n[2]*n[2];
    if(squared>1e-10f&&squared<3.4028234663852886e38f){const float inverse=1.f/std::sqrt(squared);for(std::size_t k=0;k<3;k++)s.normal_44[k]=n[k]*inverse;}
    if(!input.model_word_4)s.angle_7c=0;
    else{
        float rate=3.f,degrees=30.f;const bool air=s.contact_word_34==0||input.blend_1c3c>=1.f;
        const float curve_input=std::abs(input.speed_parameter)*3.5999999046325684f;const bool has_global_curve=!p.angle_curve_19f8.points.empty();
        const auto blended_angle=[&](float from_curve){
            const float denominator=1.f-p.reference_cd4;require(denominator!=0,"Singular wheel blend reference");
            float weight=(1.f-input.blend_1c44)/denominator;if(weight<0)weight=0;else if(weight>=1)weight=1;
            float angle=weight*p.angle_limit_118c;if(angle<=from_curve)angle=from_curve;return angle;
        };
        if(!p.material_parameters_1a48){
            if(air){if(has_global_curve)degrees=curve(p.angle_curve_19f8,curve_input);}
            else{const float from_curve=has_global_curve?curve(p.angle_curve_19f8,curve_input):30.f;degrees=blended_angle(from_curve);rate=p.angle_rate_1190;}
        }else{
            const std::size_t index=p.remap_material14_to0&&s.material_40==14?0:s.material_40;require(index<materials.size(),"Wheel material index out of range");
            const auto& material=materials[index];rate=material.angle_rate_4c;scalar(rate);
            if(air){if(has_global_curve)degrees=curve(material.angle_curve_d8,curve_input);}
            else{degrees=blended_angle(curve(material.angle_curve_d8,curve_input));rate=p.angle_rate_1190;}
        }
        s.target_angle_80=((degrees*3.1415927410125732f)/180.f)*(-input.steering_1430);
        if(s.target_angle_80<=s.angle_7c){s.angle_7c=s.angle_7c-rate*dt;if(s.angle_7c<s.target_angle_80)s.angle_7c=s.target_angle_80;}
        else{s.angle_7c=s.angle_7c+rate*dt;if(s.target_angle_80<s.angle_7c)s.angle_7c=s.target_angle_80;}
    }
    const auto& point=input.model_local_point;
    if(p.suspension_mode_238==2){
        const float old=s.length,adjusted=old-s.pending_compression;s.pending_compression=0;
        const float length=adjusted+((p.rest_length_244-adjusted)*dt)*p.relaxation_258;s.length=length;s.speed=(length-old)/dt;
        const float gap=p.pose_offset_250-length,zero=gap*0.f;pose.rotation={1,0,0,0,1,0,0,0,1};pose.translation={zero+point[0],point[1]+gap,zero+point[2]};
    }else if(p.suspension_mode_238==3){
        require(p.rest_length_244>0,"Mode 3 requires positive rest length");const float old=s.length;float adjusted=old-s.pending_compression;s.pending_compression=0;
        if(adjusted<0)adjusted=0;
        s.length=adjusted;float ratio=adjusted/p.rest_length_244;if(ratio<0)ratio=0;else if(ratio>=1)ratio=1;
        s.speed=(adjusted-old)/(p.rest_length_244*dt);s.length=(((1.f-ratio)*dt)*p.relaxation_258)+adjusted;
        const float negative=-s.length,zero=negative*0.f;pose.rotation={1,0,0,0,1,0,0,0,1};pose.translation={point[0]+zero,negative+(p.pose_offset_250+point[1]),point[2]+zero};
    }
    validate(s);bounded(pose.rotation);bounded(pose.translation);state=s;wheel_pose=pose;
}
void update_wheel_spin(WheelKinematicState& state,const WheelSpinInput& i,const WheelSpinParameters& p,float dt){
    bounded(std::array{state.spin_rate_1c,i.speed_parameter,i.scalar_98,i.scalar_9c,i.blend_1c3c,i.blend_1c40,i.model_radius_8,p.drive_d90,p.brake_d94,p.blend_d98,p.special_spin_1ef4});
    require(std::isfinite(dt)&&dt>0&&dt<=1&&i.model_radius_8>0,"Invalid wheel spin interval/radius");
    constexpr float epsilon=9.999999747378752e-6f;const bool state1=(i.state_word_176c&3)==1||(i.state_word_1370&3)==1;
    float next=state.spin_rate_1c;
    if(state.contact_word_34==0){
        float target=200.f,rate=100.f;
        if(i.future_tick_13a0==0xffffffffu||i.future_tick_13a0<=i.tick){
            if(i.scalar_9c<=epsilon||state1){
                if(i.scalar_98<=epsilon||state1){next=next*.9950000047683716f;target=0;rate=0;}
                else{target=i.scalar_98*200.f;rate=100.f;}
            }else{target=1.f-i.scalar_9c;if(target<0)target=0;else if(target>=1)target=1;rate=-100.f;}
        }
        if(epsilon<=std::abs(rate)){next=rate*dt+next;if((rate>0&&target<next)||(rate<0&&next<target))next=target;}
    }else{
        const bool special=state.material_40==74||state.material_40==3||state.material_40==21;
        if(i.override_14b8||(special&&i.scalar_98>epsilon&&!state1&&i.speed_parameter*3.5999999046325684f<50.f))next=p.special_spin_1ef4;
        else{
            const float blend=i.model_word_4?i.blend_1c3c:i.blend_1c40;float target=0,rate=0;
            if(i.scalar_9c<=epsilon){if(i.scalar_98>epsilon&&!state1){rate=next<=0&&next!=0?200.f:50.f;target=(i.scalar_98*p.drive_d90)/i.model_radius_8;}}
            else{rate=next<=0?-50.f:-200.f;target=(i.scalar_9c*p.brake_d94)/i.model_radius_8;}
            const float body_speed=i.speed_parameter/i.model_radius_8;rate=rate*(1.f-blend);
            if(std::abs(target)<std::abs(body_speed)&&std::signbit(rate)==std::signbit(body_speed))target=body_speed;
            float output=body_speed;
            if(!state1){
                if(epsilon<=std::abs(rate)){
                    next=rate*dt+next;if(rate<=0){if(next<=target)next=target;}else if(target<=next)next=target;
                }else next=(next-body_speed)*.949999988079071f+body_speed;
                const float denominator=1.0000100135803223f-p.blend_d98;require(denominator!=0,"Singular wheel spin blend denominator");
                float mix=1.f-(1.f-blend)/denominator;if(mix<=0)mix=0;output=mix*(body_speed-next)+next;
            }
            next=output;
        }
    }
    scalar(next);state.spin_rate_1c=next;
}
}
